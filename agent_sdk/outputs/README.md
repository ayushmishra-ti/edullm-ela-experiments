# Outputs Folder

This folder stores all generated outputs from the Agent SDK pipeline, including MCQ results, curriculum lookups, and batch operation results.

## File Types

### MCQ Generation Results
- **Format**: `mcq_{item_id}_{timestamp}.json`
- **Example**: `mcq_l_3_1_a_mcq_easy_001_20260122_130845.json`
- **Contents**: 
  - Request data
  - Generation result
  - Generated MCQ item(s)
  - Timestamp and metadata

### Curriculum Lookup Results
- **Format**: `curriculum_lookup_{standard_id}_{timestamp}.json`
- **Example**: `curriculum_lookup_CCSS_ELA_LITERACY_L_3_1_A_20260122_130845.json`
- **Contents**:
  - Standard ID
  - Assessment Boundaries
  - Common Misconceptions
  - Lookup metadata

### Batch Results
- **Format**: `batch_results_{timestamp}.json`
- **Example**: `batch_results_20260122_130845.json`
- **Contents**:
  - List of all generation results
  - Summary statistics (total, successful, failed)
  - Timestamp

## Usage

### Automatic Saving

When you run the test script, it automatically saves results to this folder:

```bash
python option_c_agent_sdk/tests/test_pipeline.py
```

### Manual Saving

You can also save results programmatically using the utility functions:

```python
from option_c_agent_sdk import save_mcq_result, save_curriculum_lookup, save_batch_results

# Save a single MCQ result
save_mcq_result(result, request)

# Save a curriculum lookup result
save_curriculum_lookup(lookup_result, substandard_id)

# Save batch operation results
save_batch_results([result1, result2, result3])
```

## File Structure

Each output file is a JSON file with the following structure:

### MCQ Result File
```json
{
  "timestamp": "2026-01-22T13:08:45.123456",
  "generation_mode": "agent_sdk",
  "success": true,
  "request": { ... },
  "result": { ... },
  "generated_items": [ ... ]
}
```

### Curriculum Lookup File
```json
{
  "timestamp": "2026-01-22T13:08:45.123456",
  "substandard_id": "CCSS.ELA-LITERACY.L.3.1.A",
  "lookup_result": {
    "found": true,
    "assessment_boundaries": "...",
    "common_misconceptions": [ ... ]
  }
}
```

## Cleanup

To clean old output files:
```bash
# Linux/Mac
find outputs -name "*.json" -mtime +30 -delete

# Windows PowerShell
Get-ChildItem outputs -Filter "*.json" | Where-Object {$_.LastWriteTime -lt (Get-Date).AddDays(-30)} | Remove-Item
```
