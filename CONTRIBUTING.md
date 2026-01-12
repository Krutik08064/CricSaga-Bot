# Contributing to CricSaga Bot

First off, thank you for considering contributing to CricSaga Bot! 🏏

## Code of Conduct

This project and everyone participating in it is governed by our commitment to providing a welcoming and inspiring community for all.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues. When you create a bug report, include as many details as possible:

* **Use a clear and descriptive title**
* **Describe the exact steps to reproduce the problem**
* **Provide specific examples**
* **Describe the behavior you observed and what you expected**
* **Include screenshots if applicable**
* **Note your environment** (OS, Python version, etc.)

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion:

* **Use a clear and descriptive title**
* **Provide a detailed description of the suggested enhancement**
* **Explain why this enhancement would be useful**
* **List examples of how it would work**

### Pull Requests

* Fill in the required template
* Follow the Python style guide (PEP 8)
* Include comments in your code where necessary
* Update documentation if needed
* Test your changes thoroughly
* Keep pull requests focused on a single issue

## Development Setup

1. **Fork and clone the repository**
```bash
git clone https://github.com/yourusername/cricsaga-bot.git
cd cricsaga-bot
```

2. **Create a virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up development database**
```bash
# Create test database
createdb cricsaga_dev

# Run setup scripts
./setup_database.sh  # or setup_database.ps1 on Windows
```

5. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your test bot token
```

## Coding Guidelines

### Python Style

* Follow PEP 8 style guide
* Use meaningful variable and function names
* Add docstrings to functions and classes
* Maximum line length: 100 characters
* Use type hints where applicable

### Example:
```python
async def calculate_rating_change(
    player_rating: int,
    opponent_rating: int,
    won: bool
) -> int:
    """
    Calculate ELO rating change for a match.
    
    Args:
        player_rating: Current rating of the player
        opponent_rating: Current rating of the opponent
        won: Whether the player won the match
        
    Returns:
        Rating change (positive or negative)
    """
    # Implementation here
    pass
```

### Commit Messages

* Use present tense ("Add feature" not "Added feature")
* Use imperative mood ("Move cursor to..." not "Moves cursor to...")
* Limit first line to 72 characters
* Reference issues and pull requests when relevant

**Good examples:**
```
Add ranked matchmaking system
Fix database connection pool leak
Update README with deployment instructions
```

### Testing

* Test all new features manually
* Verify anti-cheat system still works
* Check database queries are optimized
* Ensure no breaking changes to existing features

### Database Changes

If your contribution involves database changes:

1. Create a new SQL migration file
2. Document all schema changes
3. Update setup scripts
4. Test migration on clean database
5. Update documentation

## Project Structure

```
CricSaga Bot/
├── bb.py                 # Main bot file - all command handlers
├── db_handlerr.py       # Database operations
├── DATABASE_SETUP.sql   # Complete database schema
├── requirements.txt     # Dependencies
└── README.md           # Documentation
```

## Areas We Need Help With

* 🌐 **Translations** - Multi-language support
* 📊 **Statistics** - Advanced analytics features
* 🎨 **UI/UX** - Better message formatting
* 🧪 **Testing** - Unit and integration tests
* 📖 **Documentation** - Tutorials and guides
* 🔒 **Security** - Code review and improvements

## Questions?

Feel free to:
* Open an issue with your question
* Join our Telegram discussion group
* Email the maintainers

## Recognition

Contributors will be:
* Listed in README.md
* Credited in release notes
* Given contributor badge

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to CricSaga Bot! 🎉**
