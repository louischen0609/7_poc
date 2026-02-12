#!/bin/bash
cd "$(dirname "$0")"

echo "Killing server on port 8000..."
lsof -i :8000 -t 2>/dev/null | xargs kill 2>/dev/null
sleep 1

echo "Deleting product.db..."
rm -f product.db

echo "Starting server..."
/opt/homebrew/anaconda3/envs/poc/bin/uvicorn main:app --port 8000 --reload