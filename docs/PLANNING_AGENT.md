# Planning Agent - User Guide

## Overview

The Planning Agent is Ada's requirement clarification specialist. It transforms unclear user requests into complete, well-defined user stories through an interactive conversation focused on **behavioral requirements**, not technical implementation.

## Key Features

- **LLM-Driven Conversation**: Fully leverages LLM capabilities through prompt engineering
- **Behavioral Focus**: Asks about WHAT the system should do, not HOW to build it
- **Flexible Input**: Accepts natural language, partial stories, or complete stories
- **Multiple Interfaces**: CLI standalone, SDLC integration, API endpoints (coming soon)
- **Zero Code Access**: Focuses purely on requirements without reading code
- **Transparent Integration**: Optional layer that outputs standard story JSON

## Quick Start

### Standalone CLI Usage

```bash
# Interactive planning from natural language
python run_planning.py "I need users to search for products"

# Refine a partial story from file
python run_planning.py --input partial_story.json --output refined_story.json

# Specify LLM provider
python run_planning.py "Add login" --provider openai --model gpt-4
```

### SDLC Integration

```bash
# Enable Planning Agent during SDLC execution
python run_sdlc.py \
  --repo https://github.com/user/repo \
  --stories user_requests.json \
  --enable-planning
```

With `--enable-planning`, the Planning Agent will:
1. Process each user request interactively
2. Ask clarifying questions about behavior
3. Generate complete user stories
4. Pass refined stories to the CodingAgent

## How It Works

### Conversation Flow

```
User Request → Planning Agent Analyzes → Identifies Gaps → Asks Questions
                                                                 ↓
User Responds ← Question Asked ←──────────────────────────────┘
      ↓
Repeat until complete
      ↓
Output Structured Story JSON
```

### Example Session

```
$ python run_planning.py "I need password reset"

Planning Agent: Let me clarify a few things:
1. How should users request a password reset?
2. How should the reset link/code be delivered?
Your answer: 1. By entering their email. 2. Via email

Planning Agent: Got it. One more question:
3. How long should the reset link be valid?
Your answer: 1 hour

Planning Agent: Perfect! Here's your story:

Story ID: STORY-AUTO-A3F2B1C4
Title: As a user, I want to reset my password via email

Description:
Users who forget their password can request a secure reset link
sent to their email address.

Acceptance Criteria:
  1. User can enter their email to request a reset link
  2. System sends email with secure reset link
  3. Reset link expires after 1 hour
  4. User can set new password using valid link

✅ Story saved to: refined_story.json
```

## What Planning Agent Asks About

### ✅ Good Questions (Behavioral)

- **User Actions**: "What should trigger this feature?"
- **System Responses**: "What should the user see after clicking submit?"
- **Edge Cases**: "What if the email address is invalid?"
- **Constraints**: "Who can perform this action?"
- **User Flow**: "What happens next after this step?"

### ❌ Avoided Questions (Technical)

- Database schemas or table structure
- Technology choices (React, Vue, etc.)
- API endpoints or methods
- Architecture patterns
- Code structure or libraries

## Architecture

```
User Input (Natural Language or Partial JSON)
    ↓
┌─────────────────────────┐
│   Planning Agent        │
│   • Parse input         │
│   • Detect gaps         │
│   • Ask questions       │  ← LLM-driven
│   • Validate complete   │
└──────────┬──────────────┘
           │
           │ Structured Story JSON
           ▼
   SDLCOrchestrator → CodingAgent → Code
```

## Configuration

### Environment Variables

```bash
# LLM Provider (groq or openai)
GROQ_API_KEY=your_key_here
# or
OPENAI_API_KEY=your_key_here

# Optional: Max iterations (default: 10)
ADA_PLANNING_MAX_ITERATIONS=10
```

### Command-Line Options

#### `run_planning.py`

```
--input, -i          Input file (story JSON or text)
--output, -o         Output file (default: refined_story.json)
--provider           LLM provider: groq or openai
--model              Specific model to use
--max-iterations     Max conversation rounds (default: 10)
```

#### `run_sdlc.py`

```
--enable-planning    Enable Planning Agent for requirement clarification
```

## Output Format

The Planning Agent outputs standard Ada user story JSON:

```json
{
  "story_id": "STORY-AUTO-A3F2B1C4",
  "title": "As a user, I want to...",
  "description": "Detailed description of the feature",
  "acceptance_criteria": [
    "Criterion 1",
    "Criterion 2",
    "Criterion 3"
  ],
  "metadata": {
    "source": "planning_agent",
    "planning_agent_version": "1.0",
    "questions_asked": 4,
    "planning_duration_seconds": 87,
    "iterations": 3
  }
}
```

This format is **100% compatible** with existing Ada components.

## Best Practices

### For Users

1. **Start Simple**: Provide basic intent, let the agent ask for details
2. **Be Specific in Answers**: Clear answers lead to better stories
3. **Think User Perspective**: Focus on what users will see/do
4. **Iterate if Needed**: You can always re-run planning with more context

### Input Examples

**Good Inputs:**
```
"I need users to search for products"
"Add password reset functionality"
"Users should be able to export their data"
```

**Also Works:**
```json
{
  "title": "User search feature",
  "acceptance_criteria": ["Users can search"]
}
```

The agent will ask for missing details.

## Troubleshooting

### Planning Agent asks too many questions

- The LLM may need more context in initial request
- Try providing more details upfront
- Adjust `--max-iterations` if needed

### Planning Agent completes too quickly

- For simple, clear requests this is expected
- The agent skips unnecessary questions

### Story format is invalid

- Check that all required fields are present
- Ensure acceptance criteria are specific
- The agent will retry if format is invalid

## Advanced Usage

### Programmatic Usage

```python
from agents.planning_agent import PlanningAgent
from agents.interaction_handlers import CLIInteractionHandler
from agents.llm_client import LLMClient

# Initialize
llm = LLMClient(provider="groq")
agent = PlanningAgent(llm, max_iterations=10)
handler = CLIInteractionHandler()

# Run planning
result = agent.run(
    user_input="I need login",
    interaction_handler=handler,
    context={}
)

if result.success:
    story = result.output
    print(f"Story ID: {story['story_id']}")
```

### Custom Interaction Handler

```python
from agents.planning_agent import InteractionHandler

class MyHandler(InteractionHandler):
    def ask_question(self, question: str) -> str:
        # Custom UI logic
        return get_user_input(question)
    
    def show_message(self, message: str) -> None:
        # Custom display logic
        display_to_user(message)

# Use with Planning Agent
agent.run(user_input, MyHandler(), {})
```

## Roadmap

### Completed ✅
- Core Planning Agent
- CLI standalone tool
- SDLC integration
- LLM-driven conversation

### Coming Soon 🚧
- API endpoints for async planning
- Web UI chat interface
- Story templates library
- Repository context (README analysis)

### Future 🔮
- Multi-language support
- Voice input/output
- Learning from coding success rates
- Epic-level planning

## FAQs

**Q: Does Planning Agent access my code?**  
A: No. It focuses purely on behavioral requirements without reading code.

**Q: Can I skip Planning Agent?**  
A: Yes, it's optional. Omit `--enable-planning` to run normally.

**Q: What if I already have complete stories?**  
A: Planning Agent will validate and may ask minor clarifications, or pass through if complete.

**Q: How much does it cost?**  
A: Depends on LLM provider. Typically 3-6 LLM calls per story (less than coding phase).

**Q: Can I interrupt planning?**  
A: Yes, Ctrl+C will stop gracefully. State is not saved (coming soon).

## Support

For issues or questions:
- Check existing tests: `tests/test_planning_agent.py`
- Review design docs: `design_doc/planning_agent_*.md`
- Open an issue on GitHub

---

**Version**: 1.0  
**Last Updated**: March 4, 2026
