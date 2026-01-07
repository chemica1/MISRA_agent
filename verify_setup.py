"""
Quick setup verification script.
Run this to check if the environment is properly configured.
"""

import sys
from pathlib import Path

def check_imports():
    """Check if all required packages can be imported."""
    print("Checking package imports...")
    
    packages = [
        ("langgraph", "LangGraph"),
        ("langchain", "LangChain"),
        ("pydantic", "Pydantic"),
        ("pandas", "Pandas"),
        ("requests", "Requests"),
        ("dotenv", "python-dotenv")
    ]
    
    failed = []
    for module, name in packages:
        try:
            __import__(module)
            print(f"  [OK] {name}")
        except ImportError:
            print(f"  [FAIL] {name}")
            failed.append(name)
    
    return len(failed) == 0

def check_ollama():
    """Check if Ollama is accessible."""
    print("\nChecking Ollama connection...")
    
    try:
        import requests
        from src.config import settings
        
        url = f"{settings.ollama_base_url}/api/tags"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            models = response.json().get("models", [])
            print(f"  [OK] Ollama is running at {settings.ollama_base_url}")
            print(f"  Available models: {len(models)}")
            
            # Check if configured model is available
            model_names = [m.get("name", "").split(":")[0] for m in models]
            if settings.ollama_model in model_names:
                print(f"  [OK] Model '{settings.ollama_model}' is available")
            else:
                print(f"  [WARN] Model '{settings.ollama_model}' not found")
                print(f"    Available: {', '.join(model_names)}")
                print(f"    Run: ollama pull {settings.ollama_model}")
            
            return True
        else:
            print(f"  [FAIL] Ollama returned status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  [FAIL] Cannot connect to Ollama: {e}")
        print(f"    Make sure Ollama is running: ollama serve")
        return False

def check_project_structure():
    """Check if project structure is correct."""
    print("\nChecking project structure...")
    
    required_dirs = [
        "src/agent",
        "src/tools",
        "src/config",
        "tests/sample_code"
    ]
    
    required_files = [
        "src/main.py",
        "src/agent/state.py",
        "src/agent/graph.py",
        "src/agent/nodes.py",
        "src/tools/csv_parser.py",
        "src/tools/file_ops.py",
        "src/tools/code_analyzer.py",
        "src/tools/llm_client.py",
        "src/config/settings.py",
        "requirements.txt",
        ".env"
    ]
    
    all_ok = True
    
    for dir_path in required_dirs:
        if Path(dir_path).exists():
            print(f"  [OK] {dir_path}/")
        else:
            print(f"  [FAIL] {dir_path}/ - MISSING")
            all_ok = False
    
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"  [OK] {file_path}")
        else:
            print(f"  [FAIL] {file_path} - MISSING")
            all_ok = False
    
    return all_ok

def check_test_data():
    """Check if test data exists."""
    print("\nChecking test data...")
    
    from src.config import settings
    
    violations_csv = Path(settings.violations_csv)
    project_root = Path(settings.project_root)
    
    if violations_csv.exists():
        print(f"  [OK] Violations CSV: {violations_csv}")
    else:
        print(f"  [FAIL] Violations CSV not found: {violations_csv}")
        return False
    
    if project_root.exists():
        print(f"  [OK] Project root: {project_root}")
        
        # Count C files
        c_files = list(project_root.rglob("*.c"))
        print(f"    Found {len(c_files)} C files")
    else:
        print(f"  [FAIL] Project root not found: {project_root}")
        return False
    
    return True

def main():
    """Run all checks."""
    print("="*60)
    print("MISRA C Refactoring Agent - Setup Verification")
    print("="*60)
    
    checks = [
        ("Package Imports", check_imports),
        ("Project Structure", check_project_structure),
        ("Test Data", check_test_data),
        ("Ollama Connection", check_ollama)
    ]
    
    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"\n[FAIL] {name} check failed with error: {e}")
            results[name] = False
    
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)
    
    all_passed = True
    for name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status:8} {name}")
        if not passed:
            all_passed = False
    
    print("="*60)
    
    if all_passed:
        print("\n[OK] All checks passed! You're ready to run the agent.")
        print("\nTo run the agent:")
        print("  python -m src.main")
        return 0
    else:
        print("\n[WARN] Some checks failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

