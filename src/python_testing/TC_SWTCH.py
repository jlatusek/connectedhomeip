#
#    Copyright (c) 2024 Project CHIP Authors
#    All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

# See https://github.com/project-chip/connectedhomeip/blob/master/docs/testing/python.md#defining-the-ci-test-arguments
# for details about the block below.
#
# === BEGIN CI TEST ARGUMENTS ===
# test-runner-runs: run1
# test-runner-run/run1/app: ${ALL_CLUSTERS_APP}
# test-runner-run/run1/factoryreset: True
# test-runner-run/run1/quiet: True
# test-runner-run/run1/app-args: --discriminator 1234 --KVS kvs1 --trace-to json:${TRACE_APP}.json
# test-runner-run/run1/script-args: --storage-path admin_storage.json --commissioning-method on-network --discriminator 1234 --passcode 20202021 --trace-to json:${TRACE_TEST_JSON}.json --trace-to perfetto:${TRACE_TEST_PERFETTO}.perfetto --PICS src/app/tests/suites/certification/ci-pics-values
# === END CI TEST ARGUMENTS ===

import json
import logging
import queue
import time
from datetime import datetime, timedelta
from typing import Any

import chip.clusters as Clusters
import test_plan_support
from chip.clusters import ClusterObjects as ClusterObjects
from chip.clusters.Attribute import EventReadResult, TypedAttributePath
from chip.tlv import uint
from matter_testing_support import (AttributeValue, ClusterAttributeChangeAccumulator, EventChangeCallback, MatterBaseTest,
                                    TestStep, default_matter_test_main, has_feature, per_endpoint_test)
from mobly import asserts

logger = logging.getLogger(__name__)


class TC_SwitchTests(MatterBaseTest):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def desc_TC_SWTCH_2_4(self) -> str:
        """Returns a description of this test"""
        return "[TC-SWTCH-2.4] Momentary Switch Long Press Verification"

    # def steps_TC_SWTCH_2_4(self) -> list[TestStep]:
    #     steps = [
    #         TestStep("0", "Commissioning, already done", is_commissioning=True),
    #         # TODO: fill when test is done
    #     ]

    #     return steps

    def _send_named_pipe_command(self, command_dict: dict[str, Any]):
        app_pid = self.matter_test_config.app_pid
        if app_pid == 0:
            asserts.fail("The --app-pid flag must be set when usage of button simulation named pipe is required (e.g. CI)")

        app_pipe = f"/tmp/chip_all_clusters_fifo_{app_pid}"
        command = json.dumps(command_dict)

        # Sends an out-of-band command to the sample app
        with open(app_pipe, "w") as outfile:
            logging.info(f"Sending named pipe command to {app_pipe}: '{command}'")
            outfile.write(command + "\n")
        # Delay for pipe command to be processed (otherwise tests may be flaky).
        time.sleep(0.1)

    def _use_button_simulator(self) -> bool:
        return self.check_pics("PICS_SDK_CI_ONLY") or self.user_params.get("use_button_simulator", False)

    def _ask_for_switch_idle(self):
        if not self._use_button_simulator():
            self.wait_for_user_input(prompt_msg="Ensure switch is idle")

    def _send_multi_press_named_pipe_command(self, endpoint_id: int, number_of_presses: int, pressed_position: int, feature_map: uint, multi_press_max: uint):
        command_dict = {"Name": 'SimulateMultiPress', "EndpointId": endpoint_id,
                        "ButtonId": pressed_position, "MultiPressPressedTimeMillis": 500, "MultiPressReleasedTimeMillis": 500,
                        "MultiPressNumPresses": number_of_presses, "FeatureMap": feature_map, "MultiPressMax": multi_press_max}
        self._send_named_pipe_command(command_dict)

    def _send_long_press_named_pipe_command(self, endpoint_id: int, pressed_position: int, feature_map: int):
        command_dict = {"Name": "SimulateLongPress", "EndpointId": endpoint_id,
                        "ButtonId": pressed_position, "LongPressDelayMillis": 5000, "LongPressDurationMillis": 5500, "FeatureMap": feature_map}
        self._send_named_pipe_command(command_dict)

    def _ask_for_multi_press_short_long(self, endpoint_id: int, pressed_position: int, feature_map: uint, multi_press_max: uint):
        if not self._use_button_simulator():
            msg = f"""
                Actuate the switch in the following sequence:
                1. Operate switch (press briefly) associated with position {pressed_position} on the DUT then release switch from DUT
                2. Operate switch (keep pressed for long time, e.g. 5 seconds) on the DUT immediately after the previous step
                3. Release switch from the DUT
                """
            self.wait_for_user_input(msg)
        else:
            # This is just a simulator, ignore the long press instruction for now, it doesn't matter for the CI. It does for cert.
            self._send_multi_press_named_pipe_command(endpoint_id, 2, pressed_position, feature_map, multi_press_max)

    def _ask_for_multi_press_long_short(self, endpoint_id, pressed_position, feature_map: int):
        if not self._use_button_simulator():
            msg = f"""
                  Actuate the switch in the following sequence:
                  1. Operate switch (keep pressed for long time, e.g. 5 seconds) on the DUT
                  2. Releases switch from the DUT
                  3. Immediately after the previous step completes, operate switch (press briefly) associated with position {pressed_position} on the DUT then release switch from DUT
                  """
            self.wait_for_user_input(msg)
        else:
            # This is just the start of the sequence
            # we'll need to send the short press after getting the LongRelease event because the simulator doesn't queue requests.
            self._send_long_press_named_pipe_command(endpoint_id, pressed_position, feature_map)

    def _ask_for_multi_press(self, endpoint_id: int, number_of_presses: int, pressed_position: int, feature_map: uint, multi_press_max: uint):
        if not self._use_button_simulator():
            self.wait_for_user_input(
                f'Operate the switch (press briefly) associated with position {pressed_position} then release {number_of_presses} times')
        else:
            self._send_multi_press_named_pipe_command(endpoint_id, number_of_presses,
                                                      pressed_position, feature_map, multi_press_max)

    def _ask_for_long_press(self, endpoint_id: int, pressed_position: int, feature_map):
        if not self._use_button_simulator():
            self.wait_for_user_input(
                prompt_msg=f"Press switch position {pressed_position} for a long time (around 5 seconds) on the DUT, then release it.")
        else:
            self._send_long_press_named_pipe_command(endpoint_id, pressed_position, feature_map)

    def _ask_for_keep_pressed(self, endpoint_id: int, pressed_position: int, feature_map: int):
        if not self._use_button_simulator():
            self.wait_for_user_input(
                prompt_msg=f"Press switch position {pressed_position} for a long time (around 5 seconds) on the DUT, then release it.")
        else:
            self._send_long_press_named_pipe_command(endpoint_id, pressed_position, feature_map)

    def _ask_for_release(self):
        # Since we used a long press for this, "ask for release" on the button simulator just means waiting out the delay
        if not self._use_button_simulator():
            self.wait_for_user_input(
                prompt_msg="Release the button."
            )
        else:
            time.sleep(self.keep_pressed_delay/1000)

    def _placeholder_for_step(self, step_id: str):
        # TODO: Global search an replace of `self._placeholder_for_step` with `self.step` when done.
        logging.info(f"Step {step_id}")
        pass

    def _placeholder_for_skip(self, step_id: str):
        logging.info(f"Skipped step {step_id}")

    def _await_sequence_of_reports(self, report_queue: queue.Queue, endpoint_id: int, attribute: TypedAttributePath, sequence: list[Any], timeout_sec: float):
        start_time = time.time()
        elapsed = 0.0
        time_remaining = timeout_sec

        sequence_idx = 0
        actual_values = []

        while time_remaining > 0:
            expected_value = sequence[sequence_idx]
            logging.info(f"Expecting value {expected_value} for attribute {attribute} on endpoint {endpoint_id}")
            try:
                item: AttributeValue = report_queue.get(block=True, timeout=time_remaining)

                # Track arrival of all values for the given attribute.
                if item.endpoint_id == endpoint_id and item.attribute == attribute:
                    actual_values.append(item.value)

                    if item.value == expected_value:
                        logging.info(f"Got expected attribute change {sequence_idx+1}/{len(sequence)} for attribute {attribute}")
                        sequence_idx += 1
                    else:
                        asserts.assert_equal(item.value, expected_value,
                                             msg="Did not get expected attribute value in correct sequence.")

                    # We are done waiting when we have accumulated all results.
                    if sequence_idx == len(sequence):
                        logging.info("Got all attribute changes, done waiting.")
                        return
            except queue.Empty:
                # No error, we update timeouts and keep going
                pass

            elapsed = time.time() - start_time
            time_remaining = timeout_sec - elapsed

        asserts.fail(f"Did not get full sequence {sequence} in {timeout_sec:.1f} seconds. Got {actual_values} before time-out.")

    def _await_sequence_of_events(self, event_queue: queue.Queue, endpoint_id: int, sequence: list[ClusterObjects.ClusterEvent], timeout_sec: float):
        start_time = time.time()
        elapsed = 0.0
        time_remaining = timeout_sec

        sequence_idx = 0
        actual_events = []

        while time_remaining > 0:
            logging.info(f"Expecting event {sequence[sequence_idx]} on endpoint {endpoint_id}")
            try:
                item: EventReadResult = event_queue.get(block=True, timeout=time_remaining)
                expected_event = sequence[sequence_idx]
                event_data = item.Data

                if item.Header.EndpointId == endpoint_id and item.Header.ClusterId == event_data.cluster_id:
                    actual_events.append(event_data)

                    if event_data == expected_event:
                        logging.info(f"Got expected Event {sequence_idx+1}/{len(sequence)}: {event_data}")
                        sequence_idx += 1
                    else:
                        asserts.assert_equal(event_data, expected_event, msg="Did not get expected event in correct sequence.")

                    # We are done waiting when we have accumulated all results.
                    if sequence_idx == len(sequence):
                        logging.info("Got all expected events, done waiting.")
                        return
            except queue.Empty:
                # No error, we update timeouts and keep going
                pass

            elapsed = time.time() - start_time
            time_remaining = timeout_sec - elapsed

        asserts.fail(f"Did not get full sequence {sequence} in {timeout_sec:.1f} seconds. Got {actual_events} before time-out.")

    def _expect_no_events_for_cluster(self, event_queue: queue.Queue, endpoint_id: int, expected_cluster: ClusterObjects.Cluster, timeout_sec: float):
        start_time = time.time()
        elapsed = 0.0
        time_remaining = timeout_sec

        logging.info(f"Waiting {timeout_sec:.1f} seconds for no more events for cluster {expected_cluster} on endpoint {endpoint_id}")
        while time_remaining > 0:
            try:
                item: EventReadResult = event_queue.get(block=True, timeout=time_remaining)
                event_data = item.Data

                if item.Header.EndpointId == endpoint_id and item.Header.ClusterId == event_data.cluster_id and item.Header.ClusterId == expected_cluster.id:
                    asserts.fail(f"Got Event {event_data} when we expected no further events for {expected_cluster}")
            except queue.Empty:
                # No error, we update timeouts and keep going
                pass

            elapsed = time.time() - start_time
            time_remaining = timeout_sec - elapsed

        logging.info(f"Successfully waited for no further events on {expected_cluster} for {elapsed:.1f} seconds")

    @per_endpoint_test(has_feature(Clusters.Switch, Clusters.Switch.Bitmaps.Feature.kMomentarySwitch))
    async def test_TC_SWTCH_2_4(self):
        # TODO: Make this come from PIXIT
        switch_pressed_position = 1
        post_prompt_settle_delay_seconds = 10.0

        # Commission DUT - already done

        # Read feature map to set bool markers
        cluster = Clusters.Objects.Switch
        feature_map = await self.read_single_attribute_check_success(cluster, attribute=cluster.Attributes.FeatureMap)

        has_ms_feature = (feature_map & cluster.Bitmaps.Feature.kMomentarySwitch) != 0
        has_msr_feature = (feature_map & cluster.Bitmaps.Feature.kMomentarySwitchRelease) != 0
        has_msl_feature = (feature_map & cluster.Bitmaps.Feature.kMomentarySwitchLongPress) != 0
        has_as_feature = (feature_map & cluster.Bitmaps.Feature.kActionSwitch) != 0
        # has_msm_feature = (feature_map & cluster.Bitmaps.Feature.kMomentarySwitchMultiPress) != 0

        if not has_ms_feature:
            logging.info("Skipping rest of test: SWTCH.S.F01(MS) feature not present")
            self.skip_all_remaining_steps("2")

        endpoint_id = self.matter_test_config.endpoint

        # Step 1: Set up subscription to all Switch cluster events
        self._placeholder_for_step("1")
        event_listener = EventChangeCallback(cluster)
        attrib_listener = ClusterAttributeChangeAccumulator(cluster)
        await event_listener.start(self.default_controller, self.dut_node_id, endpoint=endpoint_id)
        await attrib_listener.start(self.default_controller, self.dut_node_id, endpoint=endpoint_id)

        # Step 2: Operator does not operate switch on the DUT
        self._placeholder_for_step("2")
        self._ask_for_switch_idle()

        # Step 3: TH reads the CurrentPosition attribute from the DUT
        self._placeholder_for_step("3")

        # Verify that the value is 0
        current_position = await self.read_single_attribute_check_success(cluster, attribute=cluster.Attributes.CurrentPosition)
        asserts.assert_equal(current_position, 0)

        # Step 4a: Operator operates switch (keep pressed for long time, e.g. 5 seconds) on the DUT, the release it
        self._placeholder_for_step("4a")
        self._ask_for_long_press(endpoint_id, switch_pressed_position, feature_map)

        # Step 4b: TH expects report of CurrentPosition 1, followed by a report of Current Position 0.
        self._placeholder_for_step("4b")
        logging.info(
            f"Starting to wait for {post_prompt_settle_delay_seconds:.1f} seconds for CurrentPosition to go {switch_pressed_position}, then 0.")
        self._await_sequence_of_reports(report_queue=attrib_listener.attribute_queue, endpoint_id=endpoint_id, attribute=cluster.Attributes.CurrentPosition, sequence=[
                                        switch_pressed_position, 0], timeout_sec=post_prompt_settle_delay_seconds)

        # Step 4c: TH expects at least InitialPress with NewPosition = 1
        self._placeholder_for_step("4c")
        logging.info(f"Starting to wait for {post_prompt_settle_delay_seconds:.1f} seconds for InitialPress event.")
        expected_events = [cluster.Events.InitialPress(newPosition=switch_pressed_position)]
        self._await_sequence_of_events(event_queue=event_listener.event_queue, endpoint_id=endpoint_id,
                                       sequence=expected_events, timeout_sec=post_prompt_settle_delay_seconds)

        # Step 4d: For MSL/AS, expect to see LongPress/LongRelease in that order
        if not has_msl_feature and not has_as_feature:
            logging.info("Skipping Step 4d due to missing MSL and AS features")
            self._placeholder_for_skip("4d")
        else:
            # Steb 4d: TH expects report of LongPress, LongRelease in that order.
            self._placeholder_for_step("4d")
            logging.info(f"Starting to wait for {post_prompt_settle_delay_seconds:.1f} seconds for LongPress then LongRelease.")
            expected_events = []
            expected_events.append(cluster.Events.LongPress(newPosition=switch_pressed_position))
            expected_events.append(cluster.Events.LongRelease(previousPosition=switch_pressed_position))
            self._await_sequence_of_events(event_queue=event_listener.event_queue, endpoint_id=endpoint_id,
                                           sequence=expected_events, timeout_sec=post_prompt_settle_delay_seconds)

        # Step 4e: For MS & (!MSL & !AS & !MSR), expect no further events for 10 seconds.
        if not has_msl_feature and not has_as_feature and not has_msr_feature:
            self._placeholder_for_step("4e")
            self._expect_no_events_for_cluster(event_queue=event_listener.event_queue,
                                               endpoint_id=endpoint_id, expected_cluster=cluster, timeout_sec=10.0)

        # Step 4f: For MSR & not MSL, expect to see ShortRelease.
        if not has_msl_feature and has_msr_feature:
            self._placeholder_for_step("4f")
            expected_events = [cluster.Events.ShortRelease(previousPosition=switch_pressed_position)]
            self._await_sequence_of_events(event_queue=event_listener.event_queue, endpoint_id=endpoint_id,
                                           sequence=expected_events, timeout_sec=post_prompt_settle_delay_seconds)

    def _received_event(self, event_listener: EventChangeCallback, target_event: ClusterObjects.ClusterEvent, timeout_s: int) -> bool:
        """
            Returns true if this event was received, false otherwise
        """
        remaining = timedelta(seconds=timeout_s)
        end_time = datetime.now() + remaining
        while (remaining.seconds > 0):
            try:
                event = event_listener.event_queue.get(timeout=remaining.seconds)
            except queue.Empty:
                return False

            if event.Header.EventId == target_event.event_id:
                return True
            remaining = end_time - datetime.now()
        return False

    def steps_TC_SWTCH_2_3(self):
        return [TestStep(1, test_plan_support.commission_if_required(), "", is_commissioning=True),
                TestStep(2, "Set up subscription to all events of Switch cluster on the endpoint"),
                TestStep(3, "Operator does not operate switch on the DUT"),
                TestStep(4, "TH reads the CurrentPosition attribute from the DUT", "Verify that the value is 0"),
                TestStep(5, "Operator operates switch (keep it pressed)",
                         "Verify that the TH receives InitialPress event with NewPosition set to 1 on the DUT"),
                TestStep(6, "TH reads the CurrentPosition attribute from the DUT", "Verify that the value is 1"),
                TestStep(7, "Operator releases switch on the DUT"),
                TestStep("8a", "If the DUT implements the MSR feature and does not implement the MSL feature, verify that the TH receives ShortRelease event with NewPosition set to 0 on the DUT", "Event received"),
                TestStep("8b", "If the DUT implements the MSR feature and the MSL feature, verify that the TH receives LongRelease event with NewPosition set to 0 on the DUT", "Event received"),
                TestStep(
                    "8c", "If the DUT implements the AS feature, verify that the TH does not receive ShortRelease event on the DUT", "No event received"),
                TestStep(9, "TH reads the CurrentPosition attribute from the DUT", "Verify that the value is 0"),
                ]

    @per_endpoint_test(has_feature(Clusters.Switch, Clusters.Switch.Bitmaps.Feature.kMomentarySwitch))
    async def test_TC_SWTCH_2_3(self):
        # Commissioning - already done
        self.step(1)
        cluster = Clusters.Switch
        feature_map = await self.read_single_attribute_check_success(cluster, attribute=cluster.Attributes.FeatureMap)

        has_msr_feature = (feature_map & cluster.Bitmaps.Feature.kMomentarySwitchRelease) != 0
        has_msl_feature = (feature_map & cluster.Bitmaps.Feature.kMomentarySwitchLongPress) != 0
        has_as_feature = (feature_map & cluster.Bitmaps.Feature.kActionSwitch) != 0

        endpoint_id = self.matter_test_config.endpoint

        self.step(2)
        event_listener = EventChangeCallback(cluster)
        await event_listener.start(self.default_controller, self.dut_node_id, endpoint=endpoint_id)

        self.step(3)
        self._ask_for_switch_idle()

        self.step(4)
        button_val = await self.read_single_attribute_check_success(cluster=cluster, attribute=cluster.Attributes.CurrentPosition)
        asserts.assert_equal(button_val, 0, "Button value is not 0")

        self.step(5)
        # We're using a long press here with a very long duration (in computer-land). This will let us check the intermediate values.
        # This is 1s larger than the subscription ceiling
        self.keep_pressed_delay = 6000
        self.pressed_position = 1
        self._ask_for_keep_pressed(endpoint_id, self.pressed_position, feature_map)
        event_listener.wait_for_event_report(cluster.Events.InitialPress)

        self.step(6)
        button_val = await self.read_single_attribute_check_success(cluster=cluster, attribute=cluster.Attributes.CurrentPosition)
        asserts.assert_equal(button_val, self.pressed_position, f"Button value is not {self.pressed_position}")

        self.step(7)
        self._ask_for_release()

        self.step("8a")
        if has_msr_feature and not has_msl_feature:
            asserts.assert_true(self._received_event(event_listener, cluster.Events.ShortRelease, 10),
                                "Did not receive short release")
        else:
            self.mark_current_step_skipped()

        self.step("8b")
        if has_msr_feature and has_msl_feature:
            asserts.assert_true(self._received_event(event_listener, cluster.Events.LongRelease, 10),
                                "Did not receive long release")

        self.step("8c")
        if has_as_feature:
            asserts.assert_false(self._received_event(event_listener, cluster.Events.ShortRelease, 10), "Received short release")
        else:
            self.mark_current_step_skipped()

        self.step(9)
        button_val = await self.read_single_attribute_check_success(cluster=cluster, attribute=cluster.Attributes.CurrentPosition)
        asserts.assert_equal(button_val, 0, "Button value is not 0")

    def steps_TC_SWTCH_2_5(self):
        return [TestStep(1, test_plan_support.commission_if_required(), "", is_commissioning=True),
                TestStep(2, "Set up a subscription to all Switch cluster events"),
                TestStep(3, "Operate does not operate the switch on the DUT"),
                TestStep("4a", "Operator operates switch (press briefly) associated with position 1 on the DUT then release switch from DUT",
                         """

                         * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH receives ShortRelease event with PreviousPosition set to 1 from the DUT
                        """),
                TestStep("4b", "Operator does not operate switch on the DUT",
                         "TH receives MultiPressComplete event with PreviousPosition set to 1 and TotalNumberOfPressesCounted set to 1 from the DUT"),
                TestStep("5a", "Operator repeat step 4a 2 times quickly",
                         """

                         * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH receives ShortRelease event with PreviousPosition set to 1 from the DUT
                         * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH receives MultiPressOngoing event with NewPosition set to 1 and CurrentNumberOfPressesCounted set to 2 from the DUT
                         * Verify that the TH receives ShortRelease event with PreviousPosition set to 1 from the DUT +

                         The events sequence SHALL follow the same sequence as above
                         """),
                TestStep("5b", "Operator does not operate switch on the DUT",
                         "Verify that the TH receives MultiPressComplete event with PreviousPosition set to 1 and TotalNumberOfPressesCounted set to 2 from the DUT"),
                TestStep("6a", "If MultiPressMax == 2 (see 2c of TC-SWTCH-2.1), skip steps 6b .. 6c"),
                TestStep("6b", "Operator repeat step 4a 3 times quickly",
                         """
                         * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH receives ShortRelease event with PreviousPosition set to 1 from the DUT
                         * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH receives MultiPressOngoing event with NewPosition set to 1 and CurrentNumberOfPressesCounted set to 2 from the DUT
                         * Verify that the TH receives ShortRelease event with PreviousPosition set to 1 from the DUT
                         * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH receives MultiPressOngoing event with NewPosition set to 1 and CurrentNumberOfPressesCounted set to 3 from the DUT
                         * Verify that the TH receives ShortRelease event with PreviousPosition set to 1 from the DUT +

                         The events sequence from the subscription SHALL follow the same sequence as expressed above, in the exact order of events specified.
                         """),
                TestStep("6c", "Operator does not operate switch on the DUT for 5 seconds",
                         "Verify that the TH receives MultiPressComplete event with PreviousPosition set to 1 and TotalNumberOfPressesCounted set to 3 from the DUT"),
                TestStep(7, "Set up subscription to all Switch cluster events"),
                TestStep("8a",
                         """
                         Operator operates switch in below sequence:
                         1. Operator operates switch (press briefly) associated with position 1 on the DUT then release switch from DUT
                         2. Operator operates switch (keep pressed for long time, e.g. 5 seconds) on the DUT immediately after the previous step
                         3. Operator releases switch from the DUT
                         """,
                         """

                         * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH receives ShortRelease event with PreviousPosition set to 1 from the DUT
                         * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT

                         * Verify that the TH receives MultiPressOngoing event with NewPosition set to 1 and CurrentNumberOfPressesCounted set to 2 from the DUT
                         * Verify that the TH receives ShortRelease event with PreviousPosition set to 1 from the DUT
                         * Verify that the TH does not receive LongPress event from the DUT
                         * Verify that the TH does not receive LongRelease event from the DUT

                         The events sequence from the subscription SHALL follow the same sequence as expressed above, in the exact order of events specified.
                         """),
                TestStep("8b", "Operator does not operate switch on the DUT",
                         "TH receives MultiPressComplete event with PreviousPosition set to 1 and TotalNumberOfPressesCounted set to 2 from the DUT"),
                TestStep("9a",
                         """
                         Operator operates switch in below sequence:
                         1. Operator operates switch (keep pressed for long time, e.g. 5 seconds) on the DUT
                         2. Operator releases switch from the DUT
                         3. Immediately after the previous step completes, Operator operates switch (press briefly) associated with position 1 on the DUT then release switch from DUT
                         """,
                         """

                         * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH receives (one, not more than one) LongPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH receives LongRelease event with PreviousPosition set to 1 from the DUT
                         * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH receives ShortRelease event with PreviousPosition set to 1 from the DUT
                         * Verify that the TH does not receive MultiPressOngoing event from the DUT

                         The events sequence from the subscription SHALL follow the same sequence as expressed above, in the exact order of events specified.
                         """),
                TestStep("9b", "Operator does not operate switch on the DUT",
                         "TH receives MultiPressComplete event with PreviousPosition set to 1 and TotalNumberOfPressesCounted set to 2 from the DUT")

                ]

    @staticmethod
    def should_run_SWTCH_2_5(wildcard, endpoint):
        msm = has_feature(Clusters.Switch, Clusters.Switch.Bitmaps.Feature.kMomentarySwitchMultiPress)
        asf = has_feature(Clusters.Switch, 0x20)
        return msm(wildcard, endpoint) and not asf(wildcard, endpoint)

    @per_endpoint_test(should_run_SWTCH_2_5)
    async def test_TC_SWTCH_2_5(self):
        # Commissioning - already done
        self.step(1)

        cluster = Clusters.Switch
        feature_map = await self.read_single_attribute_check_success(cluster, attribute=cluster.Attributes.FeatureMap)
        has_msl_feature = (feature_map & cluster.Bitmaps.Feature.kMomentarySwitchLongPress)
        multi_press_max = await self.read_single_attribute_check_success(cluster, attribute=cluster.Attributes.MultiPressMax)

        endpoint_id = self.matter_test_config.endpoint
        pressed_position = 1

        self.step(2)
        event_listener = EventChangeCallback(cluster)
        await event_listener.start(self.default_controller, self.dut_node_id, endpoint=endpoint_id)

        self.step(3)
        self._ask_for_switch_idle()

        def test_multi_press_sequence(starting_step: str, count: int, short_long: bool = False):
            step = starting_step
            self.step(step)

            if short_long:
                self._ask_for_multi_press_short_long(endpoint_id, pressed_position,
                                                     feature_map=feature_map, multi_press_max=multi_press_max)
            else:
                self._ask_for_multi_press(endpoint_id, number_of_presses=count, pressed_position=pressed_position,
                                          feature_map=feature_map, multi_press_max=multi_press_max)
            for i in range(count):
                event = event_listener.wait_for_event_report(cluster.Events.InitialPress)
                asserts.assert_equal(event.newPosition, pressed_position, "Unexpected NewPosition on InitialEvent")
                if i > 0:
                    event = event_listener.wait_for_event_report(cluster.Events.MultiPressOngoing)
                    asserts.assert_equal(event.newPosition, pressed_position, "Unexpected NewPosition on MultiPressOngoing")
                    asserts.assert_equal(event.currentNumberOfPressesCounted, i+1,
                                         "Unexpected CurrentNumberOfPressesCounted on MultiPressOngoing")
                event = event_listener.wait_for_event_report(cluster.Events.ShortRelease)
                asserts.assert_equal(event.previousPosition, pressed_position, "Unexpected PreviousPosition on ShortRelease")

            step = step[:-1] + chr(ord(step[-1])+1)
            self.step(step)
            self._ask_for_switch_idle()
            event = event_listener.wait_for_event_report(cluster.Events.MultiPressComplete)
            asserts.assert_equal(event.previousPosition, pressed_position, "Unexpected PreviousPosition on MultiPressComplete")
            asserts.assert_equal(event.totalNumberOfPressesCounted, count, "Unexpected count on MultiPressComplete")

        test_multi_press_sequence("4a", 1)

        test_multi_press_sequence("5a", 2)

        self.step("6a")
        multi_press_max = await self.read_single_attribute_check_success(cluster=cluster, attribute=cluster.Attributes.MultiPressMax)
        if multi_press_max == 2:
            self.skip_step("6b")
            self.skip_step("6c")
        else:
            test_multi_press_sequence("6b", 3)

        if not has_msl_feature:
            self.skip_all_remaining_steps(7)
            return

        self.step(7)
        # subscription is already set up

        test_multi_press_sequence("8a", 2, short_long=True)

        self.step("9a")
        self._ask_for_multi_press_long_short(endpoint_id, pressed_position, feature_map)

        event = event_listener.wait_for_event_report(cluster.Events.InitialPress)
        asserts.assert_equal(event.newPosition, pressed_position, "Unexpected NewPosition on InitialEvent")
        event = event_listener.wait_for_event_report(cluster.Events.LongPress)
        asserts.assert_equal(event.newPosition, pressed_position, "Unexpected NewPosition on LongPress")
        event = event_listener.wait_for_event_report(cluster.Events.LongRelease)
        asserts.assert_equal(event.previousPosition, pressed_position, "Unexpected PreviousPosition on LongRelease")
        if self._use_button_simulator:
            # simulator can't sequence so we need to help it along here
            self._send_multi_press_named_pipe_command(endpoint_id, number_of_presses=1,
                                                      pressed_position=1, feature_map=feature_map, multi_press_max=multi_press_max)

        event = event_listener.wait_for_event_report(cluster.Events.InitialPress)
        asserts.assert_equal(event.newPosition, pressed_position, "Unexpected NewPosition on InitialEvent")
        event = event_listener.wait_for_event_report(cluster.Events.ShortRelease)
        asserts.assert_equal(event.previousPosition, pressed_position, "Unexpected PreviousPosition on ShortRelease")

        # Because this is a queue, we verify that no multipress ongoing is received by verifying that the next event is the multipress complete

        self.step("9b")
        self._ask_for_switch_idle()
        event = event_listener.wait_for_event_report(cluster.Events.MultiPressComplete)
        asserts.assert_equal(event.previousPosition, pressed_position, "Unexpected PreviousPosition on MultiPressComplete")
        asserts.assert_equal(event.totalNumberOfPressesCounted, 1, "Unexpected count on MultiPressComplete")

    def steps_TC_SWTCH_2_6(self):
        return [TestStep(1, test_plan_support.commission_if_required(), is_commissioning=True),
                TestStep(2, "Set up subscription to all Switch cluster events"),
                TestStep(3, "Operator does not operate switch on the DUT"),
                TestStep("4a", "Operator operates switch (press briefly) associated with position 1 on the DUT then release switch from DUT",
                         """

                            * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT
                            * Verify that the TH does not receive ShortRelease event from the DUT
                            """),
                TestStep("4b", "Operator does not operate switch on the DUT",
                         "TH receives MultiPressComplete event with PreviousPosition set to 1 and TotalNumberOfPressesCounted set to 1 from the DUT"),
                TestStep("5a", "Operator repeat step 4a 2 times quickly",
                         """

                         * Verify that the TH receives InitialPress(one, not more than one) event with NewPosition set to 1 from the DUT
                         * Verify that the TH does not receive ShortRelease event from the DUT
                         * Verify that the TH does not receive MultiPressOngoing event from the DUT
                         """),
                TestStep("5b", "Operator does not operate switch on the DUT",
                         "Verify that the TH receives MultiPressComplete event with PreviousPosition set to 1 and TotalNumberOfPressesCounted set to 2 from the DUT"),
                TestStep("6a", "Operator repeat step 4a MultiPressMax + 1(see 2c of TC-SWTCH-2.1) times quickly",
                         """

                         * Verify that the TH receives InitialPress(one, not more than one) event with NewPosition set to 1 from the DUT
                         * Verify that the TH does not receive ShortRelease event from the DUT
                         * Verify that the TH does not receive MultiPressOngoing event from the DUT
                         """
                         ),
                TestStep("6b", "Operator does not operate switch on the DUT",
                         "Verify that the TH receives MultiPressComplete event with PreviousPosition set to 1 and TotalNumberOfPressesCounted set to 0 from the DUT"),
                TestStep("7a", "If the switch cluster does not implement the MomentarySwitchLongPress (MSL) feature, skip the remaining steps"),
                TestStep("7b", "Set up subscription to all Switch cluster events"),
                TestStep("8a",
                         """
                         Operator operates switch in below sequence:
                         1. Operator operates switch (press briefly) associated with position 1 on the DUT then release switch from DUT
                         2. Operator operates switch (keep pressed for long time, e.g. 5 seconds) on the DUT immediately after the previous step
                         3. Operator releases switch from the DUT
                         """,
                         """

                         * Verify that the TH receives InitialPress(one, not more than one) event with NewPosition set to 1 from the DUT
                         * Verify that the TH does not receive ShortRelease event from the DUT
                         * Verify that the TH does not receive MultiPressOngoing event from the DUT
                         * Verify that the TH does not receive LongPress event from the DUT
                         * Verify that the TH does not receive LongRelease event from the DUT
                         """),
                TestStep("8b", "Operator does not operate switch on the DUT",
                         "TH receives MultiPressComplete event with PreviousPosition set to 1 and TotalNumberOfPressesCounted set to 2 from the DUT"),
                TestStep("9a",
                         """
                         Operator operates switch in below sequence:

                         1. Operator operates switch (keep pressed for long time, e.g. 5 seconds) on the DUT
                         2. Operator releases switch from the DUT
                         3. Immediately after the previous step complete, Operator operates switch (press briefly) associated with position 1 on the DUT then release switch from DUT
                         """,
                         """

                         * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH receives (one, not more than one) LongPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH receives LongRelease event with PreviousPosition set to 1 from the DUT
                         * Verify that the TH receives InitialPress event with NewPosition set to 1 from the DUT
                         * Verify that the TH does not receive MultiPressOngoing event from the DUT
                         * Verify that the TH does not receive ShortRelease event from the DUT

                         The events sequence from the subscription SHALL follow the same sequence as expressed above, in the exact order of events specified.
                         """),
                TestStep("9b", "Operator does not operate switch on the DUT"
                         "Verify that the TH receives MultiPressComplete event with PreviousPosition set to 1 and TotalNumberOfPressesCounted set to 1 from the DUT"),
                ]

    @staticmethod
    def should_run_SWTCH_2_6(wildcard, endpoint):
        msm = has_feature(Clusters.Switch, Clusters.Switch.Bitmaps.Feature.kMomentarySwitchMultiPress)
        asf = has_feature(Clusters.Switch, 0x20)
        return msm(wildcard, endpoint) and asf(wildcard, endpoint)

    @per_endpoint_test(should_run_SWTCH_2_6)
    async def test_TC_SWTCH_2_6(self):
        # Commissioning - already done
        self.step(1)

        cluster = Clusters.Switch
        feature_map = await self.read_single_attribute_check_success(cluster, attribute=cluster.Attributes.FeatureMap)
        has_msl_feature = (feature_map & cluster.Bitmaps.Feature.kMomentarySwitchLongPress)
        multi_press_max = await self.read_single_attribute_check_success(cluster, attribute=cluster.Attributes.MultiPressMax)

        endpoint_id = self.matter_test_config.endpoint
        pressed_position = 1

        self.step(2)
        event_listener = EventChangeCallback(cluster)
        await event_listener.start(self.default_controller, self.dut_node_id, endpoint=endpoint_id)

        self.step(3)
        self._ask_for_switch_idle()

        def test_multi_press_sequence(starting_step: str, count: int, short_long: bool = False):
            step = starting_step
            self.step(step)

            if short_long:
                self._ask_for_multi_press_short_long(endpoint_id, pressed_position,
                                                     feature_map=feature_map, multi_press_max=multi_press_max)
            else:
                self._ask_for_multi_press(endpoint_id, number_of_presses=count, pressed_position=pressed_position,
                                          feature_map=feature_map, multi_press_max=multi_press_max)

            event = event_listener.wait_for_event_report(cluster.Events.InitialPress)
            asserts.assert_equal(event.newPosition, pressed_position, "Unexpected NewPosition on InitialEvent")

            step = step[:-1] + chr(ord(step[-1])+1)
            self.step(step)
            self._ask_for_switch_idle()
            event = event_listener.wait_for_event_report(cluster.Events.MultiPressComplete)
            asserts.assert_equal(event.previousPosition, pressed_position, "Unexpected PreviousPosition on MultiPressComplete")
            expected_count = 0 if count > multi_press_max else count
            asserts.assert_equal(event.totalNumberOfPressesCounted, expected_count, "Unexpected count on MultiPressComplete")

        test_multi_press_sequence("4a", 1)

        test_multi_press_sequence("5a", 2)

        test_multi_press_sequence("6a", multi_press_max + 1)

        self.step("7a")
        if not has_msl_feature:
            self.skip_all_remaining_steps("7b")

        # subscription is already established
        self.step("7b")

        test_multi_press_sequence("8a", 2, short_long=True)

        self.step("9a")
        self._ask_for_multi_press_long_short(endpoint_id, pressed_position, feature_map)

        event = event_listener.wait_for_event_report(cluster.Events.InitialPress)
        asserts.assert_equal(event.newPosition, pressed_position, "Unexpected NewPosition on InitialEvent")
        event = event_listener.wait_for_event_report(cluster.Events.LongPress)
        asserts.assert_equal(event.newPosition, pressed_position, "Unexpected NewPosition on LongPress")
        event = event_listener.wait_for_event_report(cluster.Events.LongRelease)
        asserts.assert_equal(event.previousPosition, pressed_position, "Unexpected PreviousPosition on LongRelease")
        if self._use_button_simulator:
            # simulator can't sequence so we need to help it along here
            self._send_multi_press_named_pipe_command(endpoint_id, number_of_presses=1,
                                                      pressed_position=1, feature_map=feature_map, multi_press_max=multi_press_max)

        event = event_listener.wait_for_event_report(cluster.Events.InitialPress)
        asserts.assert_equal(event.newPosition, pressed_position, "Unexpected NewPosition on InitialEvent")

        # Verify that we don't receive the multi-press ongoing or short release by verifying that the next event in the sequence is the multi-press complete
        self.step("9b")
        self._ask_for_switch_idle()
        event = event_listener.wait_for_event_report(cluster.Events.MultiPressComplete)
        asserts.assert_equal(event.previousPosition, pressed_position, "Unexpected PreviousPosition on MultiPressComplete")
        asserts.assert_equal(event.totalNumberOfPressesCounted, 1, "Unexpected count on MultiPressComplete")


if __name__ == "__main__":
    default_matter_test_main()
