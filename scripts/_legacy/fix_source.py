with open('app/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('"source": source_name, "location"', '"source": source, "location"')

with open('app/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed!")