@echo off
echo ========================================
echo   GoSkinning ML Training - Quick Start
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/5] Python OK
echo.

REM Install dependencies
echo [2/5] Installing dependencies...
pip install torch numpy tensorboard tqdm
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo.

REM Create sample data
echo [3/5] Creating sample data...
python create_sample_data.py --output_dir ./sample_data --num_samples 50
if errorlevel 1 (
    echo [ERROR] Failed to create sample data
    pause
    exit /b 1
)
echo.

REM Train
echo [4/5] Training (10 epochs for test)...
python training/train.py --data_dir ./sample_data/train --val_dir ./sample_data/val --model_type general --epochs 10 --batch_size 4 --output_dir ./test_checkpoints
echo.

echo [5/5] Done!
echo.
echo Model saved to: ./test_checkpoints/
echo.
echo Next steps:
echo   1. Train with real data
echo   2. Increase epochs to 100+
echo   3. Export model for 3ds Max
echo.
pause
