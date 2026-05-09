MAX_connections=100
default_timeout=30

def calculate_discount( price, rate ):
    discount=price*rate
    final_price = price-discount
    return final_price

class paymentProcessor:
    def process_Payment(self, order_id,amount):
        I = order_id
        if amount == None:
            return False
        
        if self.validate(I) == False:
            return False
            
        print("Processing payment of",amount,"for order",I)
        return True

    def validate(self, id):
        return id != None
