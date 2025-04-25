import sys
import os

print("Python executable:", sys.executable)
print("Python version:", sys.version)
print("Python path:")
for p in sys.path:
    print(f"  {p}")

try:
    import PyQt5
    print("\nPyQt5 is installed at:", PyQt5.__file__)
    print("PyQt5 version:", PyQt5.__version__)
except ImportError as e:
    print("\nFailed to import PyQt5:", e)

print("\nEnvironment variables:")
for key, value in os.environ.items():
    if "PYTHON" in key or "PATH" in key:
        print(f"  {key}: {value}")
