import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_refactorable_calculate_total():
    from refactorable_code import calculate_total
    assert calculate_total([]) == 0
    assert calculate_total([{'price': 10}, {'price': 20}]) == 30
    assert calculate_total([{'price': 0}]) == 0

def test_refactorable_processor():
    from refactorable_code import DataProcessor
    processor = DataProcessor()
    assert processor.process([1, 2, 3]) == [2, 4, 6]
    assert processor.process([]) == []

if __name__ == '__main__':
    test_refactorable_calculate_total()
    test_refactorable_processor()
    print('All inline tests passed!')
