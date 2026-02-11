
def long_function_with_high_complexity(x, y, z, a, b):
    unused_var = 42
    if x > 0:
        if y > 0:
            if z > 0:
                if a > 0:
                    if b > 0:
                        return x + y + z + a + b
    return 0

class VeryLongClassName:
    def method_with_duplicate_code(self, data):
        result = []
        for item in data:
            if item > 0:
                result.append(item * 2)
        return result
    
    def another_method_with_duplicate_code(self, data):
        result = []
        for item in data:
            if item > 0:
                result.append(item * 2)
        return result
