"""
examples/transform.py
Simple CSV transform — uppercases the 'name' column and multiplies 'value' by 10.
Used by etl_pipeline.yaml.
"""
import csv
import sys


def main():
    if len(sys.argv) != 3:
        print("Usage: transform.py <input_csv> <output_csv>", file=sys.stderr)
        sys.exit(1)

    src, dst = sys.argv[1], sys.argv[2]

    with open(src, newline="") as fin, open(dst, "w", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            row["name"] = row["name"].upper()
            row["value"] = str(int(row["value"]) * 10)
            writer.writerow(row)

    print(f"Transformed '{src}' → '{dst}'")


if __name__ == "__main__":
    main()
