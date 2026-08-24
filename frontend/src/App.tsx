import { Route, Routes } from "react-router-dom";

import { InputPage } from "./features/analysis/InputPage";
import { JobPage } from "./features/analysis/JobPage";

function App() {
  return (
    <main className="min-h-screen bg-gray-50">
      <Routes>
        <Route path="/" element={<InputPage />} />
        <Route path="/jobs/:jobId" element={<JobPage />} />
      </Routes>
    </main>
  );
}

export default App;
