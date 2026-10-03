with open('C:/Users/davfo/Desktop/job-agent/backend/app/adapt/html_renderer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the render_cv_html function
start = content.find('def render_cv_html(content: dict, job: dict | None = None, pdf_config: dict | None = None) -> str:')
if start == -1:
    print('Function not found')
else:
    # Find the end of the first function (next def or end of file)
    next_def = content.find('\ndef ', start + 1)
    if next_def == -1:
        end = len(content)
    else:
        end = next_def
    
    print(f'First function at {start} to {end}')
    print(f'Length: {end - start}')
    
    # Print the function content
    print('\n=== Function content ===')
    print(content[start:end])
    print('=== End of function ===')