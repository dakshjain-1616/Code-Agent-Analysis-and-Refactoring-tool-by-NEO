import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_divide_numbers():
    from code_with_tests import divide_numbers
    assert divide_numbers(10, 2) == 5
    assert divide_numbers(0, 5) == 0
    assert divide_numbers(5, 0) == 0
    assert divide_numbers(20, 4) == 5

if __name__ == '__main__':
    test_divide_numbers()
    print('Tests passed!')
