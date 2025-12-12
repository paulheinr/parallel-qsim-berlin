import argparse
import uuid
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def _uuid_string_to_bytes(value: str) -> bytes:
    """
    Convert a UUID representation into its 16-byte binary form.

    Supported inputs:
    - Canonical UUID strings (with or without hyphens), e.g. "018c4f3a-6d3a-7c1b-9e1d-7c7b1a2f3c4d"
    - 32-hex-digit strings, e.g. "018c4f3a6d3a7c1b9e1d7c7b1a2f3c4d"
    - Unsigned decimal integers representing a 128-bit UUID value, e.g. "2134323582035434483236795011208870033"

    The function returns 16 bytes in big-endian order (network byte order).
    """
    # Coerce to string first (defensive: pandas may pass non-str objects)
    s = str(value).strip()

    # Reject scientific-notation / float-like representations, which are not lossless for 128-bit integers
    if ("e" in s.lower()) or ("." in s):
        raise ValueError(
            f"request_id looks like a float/scientific notation ({s}). "
            "Ensure the CSV is read with request_id as a string (see converters in router_csv_to_parquet)."
        )

    # Fast-path: decimal 128-bit integer (your CSV example uses this form)
    if s.isdigit():
        n = int(s, 10)
        if n < 0 or n >= (1 << 128):
            raise ValueError(f"UUID integer out of range for 128-bit value: {s}")
        return n.to_bytes(16, byteorder="big", signed=False)

    # Otherwise, treat it as a UUID string (with or without hyphens)
    return uuid.UUID(s).bytes


def router_csv_to_parquet(csv_path: str) -> None:
    """
    Convert a CSV file with a fixed schema into a Parquet file.
    The output file will have the same name as the input file,
    but with a .parquet extension.
    """

    csv_path = Path(csv_path)
    parquet_path = csv_path.with_suffix(".parquet")

    # Define pandas dtypes (UUID is read as string first)
    pandas_dtypes = {
        "thread": "uint32",
        "now": "uint32",
        "departure_time": "uint32",
        "from": "string",
        "to": "string",
        "start": "uint64",
        "duration_ns": "uint64",
        "travel_time_s": "uint32",
        "request_id": "string",
    }

    # Read CSV
    df = pd.read_csv(
        csv_path,
        dtype=pandas_dtypes,
        keep_default_na=False,
        na_filter=False,
        engine="c",  # The pyarrow engine does not support 'converters'
    )

    # Strip whitespace from request_id defensively (keeps values as strings)
    df["request_id"] = df["request_id"].astype("string").str.strip()

    # Convert UUID string column to 16-byte binary values
    df["request_id"] = df["request_id"].map(_uuid_string_to_bytes)

    # Define explicit Arrow schema
    arrow_schema = pa.schema([
        pa.field("thread", pa.uint32()),
        pa.field("now", pa.uint32()),
        pa.field("departure_time", pa.uint32()),
        pa.field("from", pa.string()),
        pa.field("to", pa.string()),
        pa.field("start", pa.uint64()),
        pa.field("duration_ns", pa.uint64()),
        pa.field("travel_time_s", pa.uint32()),
        pa.field("request_id", pa.binary(16)),
    ])

    # Convert DataFrame to Arrow Table
    table = pa.Table.from_pandas(
        df,
        schema=arrow_schema,
        preserve_index=False
    )

    # Write Parquet file
    pq.write_table(
        table,
        parquet_path,
        compression="snappy",
        use_dictionary=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert a router CSV file to a Parquet file with a fixed schema."
    )
    parser.add_argument(
        "path",
        type=str,
        help="Path to the input CSV file"
    )

    args = parser.parse_args()
    router_csv_to_parquet(args.path)
