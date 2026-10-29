with open('pages/staff_home.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re

# We will just write a new grid for the cards that matches the requirements:
# Need Review, Missing Documents, Validity Alerts, Expiring Soon, Re-upload Required, Ready for Final Review
# and we will avoid hardcoded layout where possible.

old_grid = re.search(r'<div style="display:flex; gap: 20px; margin-bottom: 30px;">.*?</div>\s*</div>', content, re.DOTALL)

if old_grid:
    new_grid = """<div style="display:flex; flex-wrap: wrap; gap: 20px; margin-bottom: 30px;">
    <div class="card" style="flex: 1 1 30%; border-top: 4px solid #1a73e8;">
        <h2 style="margin:0; color:#1a73e8;">{need_review_count}</h2>
        <p style="margin:0;">Need Review</p>
    </div>
    <div class="card" style="flex: 1 1 30%; border-top: 4px solid #d93025;">
        <h2 style="margin:0; color:#d93025;">{missing_count}</h2>
        <p style="margin:0;">Missing Documents</p>
    </div>
    <div class="card" style="flex: 1 1 30%; border-top: 4px solid #f29900;">
        <h2 style="margin:0; color:#f29900;">0</h2>
        <p style="margin:0;">Validity Alerts</p>
    </div>
    <div class="card" style="flex: 1 1 30%; border-top: 4px solid #f29900;">
        <h2 style="margin:0; color:#f29900;">0</h2>
        <p style="margin:0;">Expiring Soon</p>
    </div>
    <div class="card" style="flex: 1 1 30%; border-top: 4px solid #d93025;">
        <h2 style="margin:0; color:#d93025;">{reupload_count}</h2>
        <p style="margin:0;">Re-upload Required</p>
    </div>
    <div class="card" style="flex: 1 1 30%; border-top: 4px solid #34a853;">
        <h2 style="margin:0; color:#34a853;">{ready_for_review_count}</h2>
        <p style="margin:0;">Ready for Final Review</p>
    </div>
</div>"""
    content = content.replace(old_grid.group(0), new_grid)

with open('pages/staff_home.py', 'w', encoding='utf-8') as f:
    f.write(content)
