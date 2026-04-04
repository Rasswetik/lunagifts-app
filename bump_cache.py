"""One-time script to bump cache busters."""
import glob

for f in glob.glob('templates/*.html'):
    with open(f, 'r', encoding='utf-8') as fh:
        content = fh.read()
    old_versions = ['v=20260403g', 'v=20260403"', 'v=20260404"', "v=20260403'", "v=20260404'"]
    new_versions = ['v=20260403h', 'v=20260403h"', 'v=20260403h"', "v=20260403h'", "v=20260403h'"]
    for old, new in zip(old_versions, new_versions):
        content = content.replace(old, new)
    with open(f, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(content)
    print(f'Updated: {f}')
