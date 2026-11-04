from django.db import models

class Customer(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True, db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.email})"


class Product(models.Model):
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sku = models.CharField(max_length=100, unique=True, db_index=True)

    def __str__(self):
        return f"{self.name} - ${self.price}"


class Order(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"Order #{self.id} for Customer {self.customer_id}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="orderItems")
    quantity = models.PositiveIntegerField(default=1)
    unitPrice = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Item {self.product_id} x {self.quantity} in Order {self.order_id}"

