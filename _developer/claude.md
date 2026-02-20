# Project Guidelines

## CRITICAL: Configuration Stability

### Never Modify Without Explicit Permission

- **Python version** - Do not change
- **Library versions** - Do not change
- **Package dependencies** - Do not change versions
- **Configuration files** - Do not modify (requirements.txt, setup.py, pyproject.toml, etc.)
- **Environment settings** - Do not alter

### Avoid Destructive Changes

- No mass refactoring to "fix" issues
- No architecture changes without discussion
- No framework upgrades or downgrades
- No changing build configurations
- No modifying deployment scripts without explicit request

### When Troubleshooting

- Work within existing configuration
- Fix code, not config
- Suggest config changes, don't implement them
- Ask before any structural changes

### Red Flags to Avoid

- "Let's upgrade to the latest version"
- "We should switch to a different library"
- "Let me restructure this to make it cleaner"
- "I'll update all the dependencies"
- Changing multiple files to solve a single issue

**If a fix requires config changes, stop and ask first.**

## Code Standards

### Python Style

- Write clean, readable code with minimal comments
- Comments only for complex logic or non-obvious decisions
- No elaborate troubleshooting comments or debug statements in production code
- Follow PEP 8 conventions

### Code Quality

- Run tests before every commit
- Fix issues completely before moving on
- Track attempted solutions to avoid repetition
- Bug tracking mode only when explicitly requested

## Project Structure

```
/tests/           # All test files
/_developer/      # Development documentation
```

## Workflow

### Branching

- Create new branches only when necessary
- Not required for minor changes or routine updates

### Testing

- Always run relevant tests before committing
- Ensure all tests pass

### Documentation

- Document significant architectural decisions
- Skip documentation for routine changes
- Keep docs in `_developer/` folder

## Communication Style

- Direct, concise responses
- No unnecessary apologies
- No verbose explanations unless requested
- Focus on solutions, not commentary

## Working on Issues

- Persist until issue is resolved
- Remember all attempted solutions
- Don't repeat failed approaches
- Ask for clarification if stuck

## Best Practices

### File Organization

- Keep related code together
- Separate concerns appropriately
- Use clear, descriptive naming

### Dependencies

- Document major dependencies
- Keep requirements up to date
- Minimize external dependencies when practical

### Error Handling

- Handle errors gracefully
- Log errors appropriately
- Don't leave debug code in production

### Performance

- Optimize when necessary
- Don't prematurely optimize
- Profile before optimizing

### Security

- Never commit secrets or credentials
- Use environment variables for sensitive data
- Keep dependencies updated for security patches

## Git Practices

- Clear, descriptive commit messages
- Atomic commits when possible
- Test before pushing
- Keep commit history clean

## Code Review

- Review your own code before submitting
- Respond to feedback constructively
- Fix issues promptly