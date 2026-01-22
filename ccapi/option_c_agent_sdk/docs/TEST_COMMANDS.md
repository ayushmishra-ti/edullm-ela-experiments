# Test Commands Reference

Quick reference guide for testing the Option C Agent SDK implementation.

## Prerequisites

```bash
# Install dependencies
pip install claude-agent-sdk

# Set API key
export ANTHROPIC_API_KEY=your-api-key  # Linux/Mac
$env:ANTHROPIC_API_KEY="your-api-key"  # Windows PowerShell
```

## Quick Tests

### 1. Test Curriculum Lookup

This test doesn't require an API key since it just reads from the curriculum file:

```bash
cd ccapi
python -c "from option_c_agent_sdk import lookup_curriculum; from pathlib import Path; result = lookup_curriculum('CCSS.ELA-LITERACY.L.3.1.A', Path('option_c_agent_sdk/data/curriculum.md')); print('Found:', result.get('found')); print('Has boundaries:', bool(result.get('assessment_boundaries'))); print('Has misconceptions:', bool(result.get('common_misconceptions')))"
```

### 2. Full Test Suite

Run the complete test suite which includes curriculum lookup, population, and MCQ generation:

```bash
cd ccapi
python option_c_agent_sdk/tests/test_pipeline.py
```

### 3. Test Curriculum Population

Test the automatic curriculum population feature:

```bash
cd ccapi
python -c "
import asyncio
from option_c_agent_sdk import populate_curriculum_entry
from pathlib import Path

async def test():
    result = await populate_curriculum_entry(
        'CCSS.ELA-LITERACY.L.3.1.A',
        Path('option_c_agent_sdk/data/curriculum.md'),
        force_regenerate=False
    )
    print('Success:', result['success'])
    print('Updated:', result['updated'])
    if result.get('assessment_boundaries'):
        print('Boundaries:', result['assessment_boundaries'][:100] + '...')
    if result.get('common_misconceptions'):
        print('Misconceptions:', len(result['common_misconceptions']), 'items')

asyncio.run(test())
"
```

### 4. Test Full MCQ Generation

Test the complete workflow from curriculum population to MCQ generation:

```bash
cd ccapi
python -c "
import asyncio
import json
from option_c_agent_sdk import generate_one_agent_sdk
from pathlib import Path

async def test():
    request = {
        'type': 'mcq',
        'grade': '3',
        'skills': {
            'substandard_id': 'CCSS.ELA-LITERACY.L.3.1.A',
            'substandard_description': 'Explain the function of nouns, pronouns, verbs, adjectives, and adverbs in general and their functions in particular sentences.'
        },
        'subject': 'ela',
        'curriculum': 'common core',
        'difficulty': 'easy'
    }
    
    result = await generate_one_agent_sdk(
        request,
        curriculum_path=Path('option_c_agent_sdk/data/curriculum.md')
    )
    
    print('Success:', result['success'])
    print('Mode:', result.get('generation_mode'))
    if result.get('error'):
        print('Error:', result['error'])
    if result.get('success'):
        items = result.get('generatedContent', {}).get('generated_content', [])
        if items:
            item = items[0]
            print('Generated MCQ ID:', item.get('id'))
            print('Question:', item.get('content', {}).get('question', '')[:100] + '...')

asyncio.run(test())
"
```

## Verify Results

### Check Curriculum File Updates

```bash
# Linux/Mac
grep -A 20 "Standard ID: CCSS.ELA-LITERACY.L.3.1.A" option_c_agent_sdk/data/curriculum.md

# Windows PowerShell
Select-String -Path "option_c_agent_sdk/data/curriculum.md" -Pattern "Standard ID: CCSS.ELA-LITERACY.L.3.1.A" -Context 0,20
```

## Expected Output

### Curriculum Lookup
- `Found: True` if the standard exists in the curriculum file
- `Has boundaries: True/False` (False if the standard hasn't been populated yet)
- `Has misconceptions: True/False` (False if the standard hasn't been populated yet)

### Curriculum Population
- `Success: True` if generation completed successfully
- `Updated: True` on first population, `False` if data already existed
- The boundaries and misconceptions text will be printed

### MCQ Generation
- `Success: True` if the question was generated successfully
- `Mode: agent_sdk` indicates the Agent SDK pipeline was used
- The generated MCQ will include an ID, question text, answer, and four options
