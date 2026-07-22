AirView AI final deliverable contents

1. Source code: backend, frontend, ml, data, models, scripts, docs.
2. Main demo UI: http://127.0.0.1:5173/dashboard after scripts/run_demo.ps1.
3. Detailed document: outputs/submission/AirViewAI_Detailed_Document.pdf.
4. Presentation deck: outputs/submission/AirViewAI_Presentation_Deck.pptx.
5. Architecture diagram: docs/architecture/assets/airview-final-architecture.png and .svg.
6. Demo script: docs/submission/demo-video-script.md.

Recommended local workflow on Windows PowerShell:
- Copy your backend/.env file if this package was extracted without secrets.
- .\scripts\run_demo.ps1
- .\scripts\verify_demo.ps1
- open http://127.0.0.1:5173/dashboard
- .\scripts\stop_demo.ps1
