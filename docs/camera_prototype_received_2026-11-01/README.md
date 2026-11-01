# Eye-closure demo

This is a local-only browser prototype using the 68-point dlib landmark model.
It estimates eye closure from eye landmarks; it does **not** detect or diagnose
syncope, loss of consciousness, or any other medical condition. Do not rely on
it for medical decisions or emergency monitoring.

## Requirements

- Python 3.10 or newer
- The actual `shape_predictor_68_face_landmarks.dat` model file
- Git LFS to download the model if the file in this checkout is only a pointer

## Run locally

From this directory in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000> and allow camera access. The server binds to
localhost only; camera frames are sent to that local server for analysis.

If the model file contains a short Git LFS pointer instead of the model data,
install Git LFS, then from the repository root run:

```powershell
git lfs pull --include="Desktop/modele/shape_predictor_68_face_landmarks.dat"
```

Start the app again after the model file has been downloaded. On Windows,
installing `dlib` may require CMake and the Visual C++ build tools if a
compatible wheel is not available for your Python version.
