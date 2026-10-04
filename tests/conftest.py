from pathlib import Path
import pytest
from quiz_app.config import load_settings
from quiz_app.models import Question

@pytest.fixture
def settings():
    return load_settings(Path(__file__).parents[1] / '.env.example')

@pytest.fixture
def question():
    return Question(id='capital', question='Capital?', answer='Paris', aliases=['Ville de Paris'])
