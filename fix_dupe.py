with open("pages/document_review.py", "r", encoding="utf-8") as f:
    content = f.read()

# We will find the FIRST block starting with `    st.write("### Verification History")`
# and ending right before `    elif status == 'Rejected':`
import re

pattern = re.compile(r'(    st\.write\("### Verification History"\).*?)(    elif status == \'Rejected\':)', re.DOTALL)

match = pattern.search(content)
if match:
    # Delete the matched block, leaving only the elif
    new_content = content.replace(match.group(1), "")
    with open("pages/document_review.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Successfully deleted the duplicate block.")
else:
    print("Could not find the block to delete.")
