import os
import subprocess
import sys
import tempfile


def execute_python_code(code: str) -> dict:
    """Execute Python code and return the output"""
    try:
        # Create a temporary file for the code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file_path = f.name
        
        # Execute the code
        result = subprocess.run(
            [sys.executable, temp_file_path],
            capture_output=True,
            text=True,
            timeout=30  # 30 seconds timeout
        )
        
        # Clean up the temporary file
        os.unlink(temp_file_path)
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        # Clean up the temporary file if timeout
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        return {
            "error": "Execution timed out after 30 seconds"
        }
    except Exception as e:
        # Clean up the temporary file if error
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        return {
            "error": str(e)
        }
