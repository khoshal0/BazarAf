import { ArrowLeft, Package, Phone, MessageCircle, MapPin, CheckCircle, Circle } from 'lucide-react';
import { Button } from '@/app/components/ui/button';
import { Card } from '@/app/components/ui/card';
import { Badge } from '@/app/components/ui/badge';
import { Separator } from '@/app/components/ui/separator';
import { mockOrders } from '@/app/data/mock-data';

interface OrderTrackingProps {
  onNavigate: (page: string, data?: any) => void;
  orderId?: string;
}

export function OrderTracking({ onNavigate, orderId }: OrderTrackingProps) {
  // Use the first mock order as default
  const order = mockOrders[0];

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'delivered':
        return 'bg-green-100 text-green-700 border-green-200';
      case 'shipped':
        return 'bg-blue-100 text-blue-700 border-blue-200';
      case 'confirmed':
        return 'bg-yellow-100 text-yellow-700 border-yellow-200';
      case 'pending':
        return 'bg-orange-100 text-orange-700 border-orange-200';
      case 'cancelled':
        return 'bg-red-100 text-red-700 border-red-200';
      default:
        return 'bg-gray-100 text-gray-700 border-gray-200';
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" onClick={() => onNavigate('home')}>
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <h2>Order Tracking</h2>
          </div>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
        {/* Order Info */}
        <Card className="p-6 bg-white">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h3 className="mb-1">Order {orderId || order.id}</h3>
              <p className="text-sm text-muted-foreground">Placed on {order.date}</p>
            </div>
            <Badge variant="outline" className={getStatusColor(order.status)}>
              {order.status.charAt(0).toUpperCase() + order.status.slice(1)}
            </Badge>
          </div>

          <Separator className="my-4" />

          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Payment Method:</span>
              <span className="font-medium">{order.paymentMethod}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Total Amount:</span>
              <span className="font-semibold text-primary">AFN {order.total.toLocaleString()}</span>
            </div>
          </div>
        </Card>

        {/* Tracking Steps */}
        <Card className="p-6 bg-white">
          <h3 className="mb-6">Tracking Status</h3>
          <div className="space-y-6">
            {order.trackingSteps.map((step, index) => (
              <div key={index} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center ${
                      step.completed ? 'bg-primary' : 'bg-gray-200'
                    }`}
                  >
                    {step.completed ? (
                      <CheckCircle className="w-6 h-6 text-white" />
                    ) : (
                      <Circle className="w-6 h-6 text-gray-400" />
                    )}
                  </div>
                  {index < order.trackingSteps.length - 1 && (
                    <div
                      className={`w-0.5 flex-1 min-h-[40px] ${
                        step.completed ? 'bg-primary' : 'bg-gray-200'
                      }`}
                    />
                  )}
                </div>
                <div className="flex-1 pb-6">
                  <div className={`font-medium mb-1 ${step.completed ? 'text-foreground' : 'text-muted-foreground'}`}>
                    {step.status}
                  </div>
                  {step.date && (
                    <div className="text-sm text-muted-foreground">{step.date}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Delivery Address */}
        <Card className="p-6 bg-white">
          <div className="flex items-center gap-2 mb-3">
            <MapPin className="w-5 h-5 text-primary" />
            <h3>Delivery Address</h3>
          </div>
          <p className="text-muted-foreground">{order.deliveryAddress}</p>
        </Card>

        {/* Order Items */}
        <Card className="p-6 bg-white">
          <h3 className="mb-4">Order Items</h3>
          <div className="space-y-4">
            {order.items.map((item) => (
              <div key={item.id} className="flex gap-4">
                <div className="w-20 h-20 bg-gray-100 rounded flex-shrink-0">
                  <img
                    src={`https://source.unsplash.com/150x150/?${item.image}`}
                    alt={item.name}
                    className="w-full h-full object-cover rounded"
                  />
                </div>
                <div className="flex-1">
                  <div className="font-medium mb-1">{item.name}</div>
                  <div className="text-sm text-muted-foreground mb-1">
                    Quantity: {item.quantity}
                  </div>
                  <div className="font-medium text-primary">
                    AFN {(item.price * item.quantity).toLocaleString()}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <Separator className="my-4" />

          <div className="flex justify-between font-semibold">
            <span>Total</span>
            <span className="text-primary">AFN {order.total.toLocaleString()}</span>
          </div>
        </Card>

        {/* Support */}
        <Card className="p-6 bg-gradient-to-r from-primary/5 to-secondary/5 border-primary/20">
          <h3 className="mb-3">Need Help?</h3>
          <p className="text-sm text-muted-foreground mb-4">
            Our customer support team is here to help you with any questions about your order.
          </p>
          <div className="flex gap-3">
            <Button className="flex-1" variant="outline">
              <Phone className="w-4 h-4 mr-2" />
              Call Support
            </Button>
            <Button className="flex-1 bg-green-600 hover:bg-green-700">
              <MessageCircle className="w-4 h-4 mr-2" />
              WhatsApp
            </Button>
          </div>
        </Card>

        {/* Actions */}
        <div className="flex gap-3">
          <Button variant="outline" className="flex-1" onClick={() => onNavigate('home')}>
            Continue Shopping
          </Button>
          <Button variant="outline" className="flex-1">
            View All Orders
          </Button>
        </div>
      </div>
    </div>
  );
}
