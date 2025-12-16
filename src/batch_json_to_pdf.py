"""
Batch convert multiple JSON files containing markdown to PDFs.
"""

import os
import sys
from pathlib import Path
from json_to_pdf import convert_json_to_pdf


def batch_convert_json_to_pdf(json_files: list, output_dir: str = None, method: str = 'reportlab'):
    """
    Convert multiple JSON files to PDF.

    Args:
        json_files: List of JSON file paths
        output_dir: Directory to save PDFs (optional, saves next to JSON if not provided)
        method: Conversion method ('reportlab', 'pdfkit', or 'pandoc')
    """
    # Create output directory if specified
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    success_count = 0
    failed_files = []

    for json_path in json_files:
        print(f"\nProcessing: {json_path}")

        # Determine output path
        if output_dir:
            json_file = Path(json_path)
            output_pdf = os.path.join(output_dir, json_file.stem + '.pdf')
        else:
            output_pdf = None  # Will be auto-generated next to JSON file

        # Convert
        if convert_json_to_pdf(json_path, output_pdf, method):
            success_count += 1
        else:
            failed_files.append(json_path)

    # Summary
    print("\n" + "=" * 60)
    print(f"Conversion complete: {success_count}/{len(json_files)} files successful")
    if failed_files:
        print(f"\nFailed files:")
        for f in failed_files:
            print(f"  - {f}")
    print("=" * 60)


def main():
    """
    Main function for batch conversion.
    """
    if len(sys.argv) < 2:
        print("Usage: python batch_json_to_pdf.py <json_file1> [json_file2] ... [options]")
        print("\nOptions:")
        print("  --output-dir <dir>  : Directory to save PDFs")
        print("  --method <method>   : Conversion method (weasyprint or pandoc)")
        print("\nExamples:")
        print("  python batch_json_to_pdf.py file1.json file2.json file3.json")
        print("  python batch_json_to_pdf.py *.json --output-dir ./pdfs")
        print("  python batch_json_to_pdf.py file*.json --method pandoc")
        sys.exit(1)

    # Parse arguments
    json_files = []
    output_dir = None
    method = 'reportlab'

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--output-dir':
            if i + 1 < len(sys.argv):
                output_dir = sys.argv[i + 1]
                i += 2
            else:
                print("Error: --output-dir requires a directory path")
                sys.exit(1)
        elif arg == '--method':
            if i + 1 < len(sys.argv):
                method = sys.argv[i + 1]
                i += 2
            else:
                print("Error: --method requires a method name")
                sys.exit(1)
        else:
            # Check if file exists
            if os.path.exists(arg):
                json_files.append(arg)
            else:
                print(f"Warning: File not found, skipping: {arg}")
            i += 1

    if not json_files:
        print("Error: No valid JSON files provided")
        sys.exit(1)

    print(f"Found {len(json_files)} JSON files to process")
    print(f"Method: {method}")
    if output_dir:
        print(f"Output directory: {output_dir}")

    batch_convert_json_to_pdf(json_files, output_dir, method)


if __name__ == '__main__':
    main()
