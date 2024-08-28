import argparse
from jinja2 import Template


def parse_args():
    parser = argparse.ArgumentParser(description="Render Jinja template with dynamic variables.")
    parser.add_argument("template", help="Path to the Jinja template file")
    parser.add_argument("output", help="Path to the output file")

    # Argumenty dodatkowe w postaci --nazwa=wartość
    parser.add_argument("--variables", nargs='*', help="Key-value pairs for template variables, in the format key=value")

    args = parser.parse_args()
    return args


def main():
    args = parse_args()

    with open(args.template, 'r') as template_file:
        template_content = template_file.read()

    template = Template(template_content)

    variables = {}
    if args.variables:
        for var in args.variables:
            key, value = var.split('=', 1)
            if value.isdigit():
                value = int(value)
            elif value.lower() == 'true':
                value = True
            elif value.lower() == 'false':
                value = False
            variables[key] = value

    output_content = template.render(variables)

    with open(args.output, 'w') as output_file:
        output_file.write(output_content)


if __name__ == "__main__":
    main()
