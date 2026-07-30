import { Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing.jsx'
import Auth from './pages/Auth.jsx'
import CreateCollective from './pages/CreateCollective.jsx'
import AcceptInvite from './pages/AcceptInvite.jsx'
import CollectiveShell from './pages/CollectiveShell.jsx'
import Home from './pages/Home.jsx'
import Ledger from './pages/Ledger.jsx'
import MyRecord from './pages/MyRecord.jsx'
import PayDues from './pages/PayDues.jsx'
import Expenses from './pages/Expenses.jsx'
import SubmitExpense from './pages/SubmitExpense.jsx'
import ExpenseDetail from './pages/ExpenseDetail.jsx'
import Approvals from './pages/Approvals.jsx'
import NeedsReview from './pages/NeedsReview.jsx'
import Members from './pages/Members.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Auth />} />
      <Route path="/create" element={<CreateCollective />} />
      <Route path="/join/:collectiveId/:memberId" element={<AcceptInvite />} />
      <Route path="/c/:collectiveId" element={<CollectiveShell />}>
        <Route index element={<Home />} />
        <Route path="ledger" element={<Ledger />} />
        <Route path="me" element={<MyRecord />} />
        <Route path="pay" element={<PayDues />} />
        <Route path="expenses" element={<Expenses />} />
        <Route path="expenses/new" element={<SubmitExpense />} />
        <Route path="expenses/:expenseId" element={<ExpenseDetail />} />
        <Route path="approvals" element={<Approvals />} />
        <Route path="review" element={<NeedsReview />} />
        <Route path="members" element={<Members />} />
      </Route>
    </Routes>
  )
}
