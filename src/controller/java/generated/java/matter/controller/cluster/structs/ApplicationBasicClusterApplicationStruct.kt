/*
 *
 *    Copyright (c) 2023 Project CHIP Authors
 *
 *    Licensed under the Apache License, Version 2.0 (the "License");
 *    you may not use this file except in compliance with the License.
 *    You may obtain a copy of the License at
 *
 *        http://www.apache.org/licenses/LICENSE-2.0
 *
 *    Unless required by applicable law or agreed to in writing, software
 *    distributed under the License is distributed on an "AS IS" BASIS,
 *    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *    See the License for the specific language governing permissions and
 *    limitations under the License.
 */
package matter.controller.cluster.structs

import matter.controller.cluster.*
import matter.tlv.ContextSpecificTag
import matter.tlv.Tag
import matter.tlv.TlvReader
import matter.tlv.TlvWriter

class ApplicationBasicClusterApplicationStruct(
  val catalogVendorID: UShort,
  val applicationID: String,
) {
  override fun toString(): String = buildString {
    append("ApplicationBasicClusterApplicationStruct {\n")
    append("\tcatalogVendorID : $catalogVendorID\n")
    append("\tapplicationID : $applicationID\n")
    append("}\n")
  }

  fun toTlv(tlvTag: Tag, tlvWriter: TlvWriter) {
    tlvWriter.apply {
      startStructure(tlvTag)
      put(ContextSpecificTag(TAG_CATALOG_VENDOR_I_D), catalogVendorID)
      put(ContextSpecificTag(TAG_APPLICATION_I_D), applicationID)
      endStructure()
    }
  }

  companion object {
    private const val TAG_CATALOG_VENDOR_I_D = 0
    private const val TAG_APPLICATION_I_D = 1

    fun fromTlv(tlvTag: Tag, tlvReader: TlvReader): ApplicationBasicClusterApplicationStruct {
      tlvReader.enterStructure(tlvTag)
      val catalogVendorID = tlvReader.getUShort(ContextSpecificTag(TAG_CATALOG_VENDOR_I_D))
      val applicationID = tlvReader.getString(ContextSpecificTag(TAG_APPLICATION_I_D))

      tlvReader.exitContainer()

      return ApplicationBasicClusterApplicationStruct(catalogVendorID, applicationID)
    }
  }
}
