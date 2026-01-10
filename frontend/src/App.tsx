import React from 'react'
import './App.css'
import UniversalUploader from './components/UniversalUploader'

function App() {
  return (
    <div className="min-h-screen" style={{ backgroundColor: '#f5f7f3' }}>
      <div className="container mx-auto px-4 py-8">
        <UniversalUploader />
      </div>
    </div>
  )
}

export default App
