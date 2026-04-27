import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import StaffLayout from './components/StaffLayout'
import Cart from './pages/Cart'
import Checkout from './pages/Checkout'
import Login from './pages/Login'
import OrderDetail from './pages/OrderDetail'
import Orders from './pages/Orders'
import PaymentReturn from './pages/PaymentReturn'
import ProductDetail from './pages/ProductDetail'
import Products from './pages/Products'
import RecommendedForYou from './pages/RecommendedForYou'
import Register from './pages/Register'
import StaffLogin from './pages/StaffLogin'
import StaffProducts from './pages/StaffProducts'
import './App.css'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Products />} />
        <Route path="/recommended" element={<RecommendedForYou />} />
        <Route path="/products/:id" element={<ProductDetail />} />
        <Route path="/cart" element={<Cart />} />
        <Route path="/checkout" element={<Checkout />} />
        <Route path="/payment-return" element={<PaymentReturn />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/orders/:id" element={<OrderDetail />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>

      <Route path="/staff" element={<StaffLayout />}>
        <Route path="login" element={<StaffLogin />} />
        <Route path="products" element={<StaffProducts />} />
        <Route index element={<Navigate to="/staff/products" replace />} />
      </Route>
    </Routes>
  )
}
