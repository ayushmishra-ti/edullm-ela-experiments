# Option B: Skills API with Code Execution

This folder will contain the implementation using **Skills API with Code Execution** for MCQ generation.

## Overview

This approach uses:
- Skills API (container-based skills)
- Code execution tool (`code_execution_20250825`)
- Curriculum lookup script that Claude can execute

## Status

**Not yet implemented** - This is a placeholder for future work.

## Planned Implementation

1. **Upload curriculum.md to skill container**
2. **Create lookup_curriculum.py script** in the skill
3. **Update SKILL.md** to instruct Claude to use the script
4. **Test** with Skills API beta features

## Challenges

- Skills API with code_execution is still in beta
- Claude may not reliably execute scripts unless explicitly prompted
- Requires careful prompt engineering to ensure script execution

## Next Steps

1. Create skill structure with curriculum.md
2. Write lookup_curriculum.py script
3. Update SKILL.md with code execution instructions
4. Test with Skills API
