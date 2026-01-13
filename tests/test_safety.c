// Test C file for MISRA safety check verification

// Test Case 1: SAFE - Adding const qualifier (should be fixed)
void safe_function_1(void) {
  int x = 10; // MISRA: should be const
  int y = x + 5;
}

// Test Case 2: UNSAFE - Would require return type change (should be skipped)
void unsafe_function_return(void) {
  // MISRA Rule 17.7: Return value should be used
  // Fixing this would require changing void to int
  int result = 42;
}

// Test Case 3: UNSAFE - Would require parameter change (should be skipped)
void unsafe_function_param(int x) {
  // MISRA: Parameter should be const
  // But this is called from many places, changing signature is risky
  int y = x * 2;
}

// Test Case 4: SAFE - Local variable naming (should be fixed)
void safe_function_2(void) {
  int X = 5; // MISRA: Variable names should be lowercase
}
