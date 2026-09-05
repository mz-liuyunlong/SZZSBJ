import { useState } from 'react'
import MainLayout from './layouts/MainLayout'
import LoginPage from './pages/auth/LoginPage'

function App() {
  const [mockLoggedIn, setMockLoggedIn] = useState(false)

  return mockLoggedIn ? (
    <MainLayout onLogout={() => setMockLoggedIn(false)} />
  ) : (
    <LoginPage onLogin={() => setMockLoggedIn(true)} />
  )
}

export default App
