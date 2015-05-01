#!/bin/sh
echo "compiling..."
python compile.py & pid=$!
wait $pid
echo "copying files..."
sudo rm -r mincompiled 2>/dev/null
mkdir mincompiled
cp -r min mincompiled/ & pid=$!
wait $pid
echo "reverting .py files"
chmod +x ./mincompiled/min/pxplistmon.pyc
echo "removing .py files..."
find ./mincompiled -name "*.py" -print0 | xargs -0 rm
find ./mincompiled -name ".DS*" -print0 | xargs -0 rm
cp min/index.py mincompiled/min/
echo "compressing the files..."
cd mincompiled
cd min
sudo rm -rf .git
find ./ -name ".git*" -print0 | xargs -0 rm
cd ..
tar -czf 04-1-min.tar.gz min/
echo "done"
