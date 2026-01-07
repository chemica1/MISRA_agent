"""CSV parser for violations file."""

import pandas as pd
from pathlib import Path
from typing import List
from ..agent.state import Violation


def parse_violations_csv(csv_path: str) -> List[Violation]:
    """
    Parse violations CSV file and return list of Violation objects.
    
    Args:
        csv_path: Path to violations.csv file
        
    Returns:
        List of Violation objects
        
    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV has missing required columns
    """
    csv_file = Path(csv_path)
    
    if not csv_file.exists():
        raise FileNotFoundError(f"Violations CSV not found: {csv_path}")
    
    # Read CSV
    df = pd.read_csv(csv_file)
    
    # Validate required columns
    required_columns = {"file_path", "function_name", "violation_description"}
    missing_columns = required_columns - set(df.columns)
    
    if missing_columns:
        raise ValueError(f"CSV missing required columns: {missing_columns}")
    
    # Convert to Violation objects
    violations = []
    for _, row in df.iterrows():
        try:
            violation = Violation(
                file_path=str(row["file_path"]).strip(),
                function_name=str(row["function_name"]).strip(),
                violation_description=str(row["violation_description"]).strip()
            )
            violations.append(violation)
        except Exception as e:
            print(f"[WARNING] Skipping invalid row: {e}")
            continue
    
    return violations
