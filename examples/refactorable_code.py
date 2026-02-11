def calculate_total(items):
    if items:
        if len(items) > 0:
            total = 0
            for item in items:
                if item:
                    if 'price' in item:
                        if item['price'] > 0:
                            total += item['price']
            return total
    return 0

class DataProcessor:
    def process(self, data):
        result = []
        for i in range(len(data)):
            if data[i] > 0:
                result.append(data[i] * 2)
        return result