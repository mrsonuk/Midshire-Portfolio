import { NavLink, Route, Routes } from 'react-router-dom'
import ExecBrief from './pages/ExecBrief'

// The React shell. Surfaces are ported here one at a time (strangler-fig);
// the links on the right go to the existing template pages until each moves.
export default function App() {
  return (
    <>
      <header className="app">
        <div className="logo">NHS</div>
        <div>
          <h1>Model ED Optimiser</h1>
          <p>Design, staff and run a high-performing emergency department</p>
        </div>
      </header>
      <nav className="app">
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
          Executive brief
        </NavLink>
        <a href="/">Control tower</a>
        <a href="/planner">Plan ahead</a>
        <a href="/analyst">Analyst view</a>
      </nav>
      <div className="wrap">
        <Routes>
          <Route path="/" element={<ExecBrief />} />
        </Routes>
      </div>
    </>
  )
}
