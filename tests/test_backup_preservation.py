"""Test to verify backup file behavior with multiple modifications."""

import tempfile
import shutil
from pathlib import Path


def backup_file(file_path: Path) -> Path:
    """
    Create backup of file with .bak extension.
    Only creates backup if one doesn't already exist to preserve original content.
    
    Args:
        file_path: Path to file to backup
        
    Returns:
        Path to backup file
    """
    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
    
    # Only create backup if it doesn't already exist
    # This preserves the original file content across multiple modifications
    if file_path.exists() and not backup_path.exists():
        shutil.copy2(file_path, backup_path)
        print(f"[BACKUP] Created: {backup_path}")
    elif backup_path.exists():
        print(f"[BACKUP] Already exists (preserving original): {backup_path}")
    
    return backup_path


def test_backup_preservation():
    """Test that backup file is created only once and preserved across multiple writes."""
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.c"
        backup_file_path = Path(tmpdir) / "test.c.bak"
        
        # Create initial file
        original_content = "// Original content\nint main() { return 0; }"
        test_file.write_text(original_content, encoding="utf-8")
        
        print("=" * 60)
        print("TEST: Backup File Preservation Across Multiple Modifications")
        print("=" * 60)
        
        # First modification
        print("\n[TEST] First modification...")
        backup_file(test_file)
        modified_content_1 = "// First modification\nint main() { return 0; }"
        test_file.write_text(modified_content_1, encoding="utf-8")
        
        # Check backup was created
        assert backup_file_path.exists(), "Backup file should be created"
        backup_content = backup_file_path.read_text(encoding="utf-8")
        assert backup_content == original_content, "Backup should contain original content"
        print("[PASS] Backup created with original content")
        
        # Second modification
        print("\n[TEST] Second modification...")
        backup_file(test_file)
        modified_content_2 = "// Second modification\nint main() { return 0; }"
        test_file.write_text(modified_content_2, encoding="utf-8")
        
        # Check backup still contains original content
        backup_content_after_2nd = backup_file_path.read_text(encoding="utf-8")
        assert backup_content_after_2nd == original_content, "Backup should STILL contain original content"
        print("[PASS] Backup preserved (not overwritten)")
        
        # Third modification
        print("\n[TEST] Third modification...")
        backup_file(test_file)
        modified_content_3 = "// Third modification\nint main() { return 0; }"
        test_file.write_text(modified_content_3, encoding="utf-8")
        
        # Check backup STILL contains original content
        backup_content_after_3rd = backup_file_path.read_text(encoding="utf-8")
        assert backup_content_after_3rd == original_content, "Backup should STILL contain original content"
        print("[PASS] Backup preserved across multiple modifications")
        
        # Verify current file has latest content
        current_content = test_file.read_text(encoding="utf-8")
        assert current_content == modified_content_3, "Current file should have latest modifications"
        print("[PASS] Current file has latest modifications")
        
        print("\n" + "=" * 60)
        print("[SUCCESS] ALL TESTS PASSED")
        print("=" * 60)
        print("\nSummary:")
        print(f"  - Original content: {len(original_content)} chars")
        print(f"  - Backup content:   {len(backup_content_after_3rd)} chars")
        print(f"  - Current content:  {len(current_content)} chars")
        print(f"  - Backup preserved: {backup_content_after_3rd == original_content}")


if __name__ == "__main__":
    test_backup_preservation()
