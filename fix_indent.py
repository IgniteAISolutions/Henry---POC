with open('app/main.py', 'r') as f:
    lines = f.readlines()

# Fix lines 287-291 indentation (16 spaces instead of 20)
for i in [286, 287, 289, 290]:
    if i < len(lines):
        lines[i] = lines[i].replace('                ', '            ', 1)

with open('app/main.py', 'w') as f:
    f.writelines(lines)
print("Fixed!")
