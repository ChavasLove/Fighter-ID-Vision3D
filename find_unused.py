import os

used = set()

for root, _, files in os.walk("."):
    for f in files:
        if f.endswith(".py"):
            with open(os.path.join(root, f), encoding="utf-8") as file:
                content = file.read()
                for line in content.splitlines():
                    if "import" in line:
                        used.add(line)

print("\nPOSIBLES ARCHIVOS NO REFERENCIADOS:")
for root, _, files in os.walk("."):
    for f in files:
        if f.endswith(".py") and f not in str(used):
            print(f)
