from __future__ import annotations
from pathlib import Path
import sys, json
sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.services.prediction_service import PredictionService
from app.config import MODEL_METRICS

def main():
    bundle = PredictionService().train()
    print('trained AI4I model')
    if MODEL_METRICS.exists():
        print(MODEL_METRICS.read_text(encoding='utf-8'))
if __name__ == '__main__': main()
