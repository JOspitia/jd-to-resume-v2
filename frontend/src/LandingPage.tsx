import { motion } from 'framer-motion';
import { ArrowRight, Code, Sparkles } from 'lucide-react';

export default function LandingPage({ onStart }: { onStart: () => void }) {
  const techStack = [
    { name: "React", iconUrl: "https://cdn.simpleicons.org/react/61DAFB" },
    { name: "Vite", iconUrl: "https://cdn.simpleicons.org/vite/646CFF" },
    { name: "TypeScript", iconUrl: "https://cdn.simpleicons.org/typescript/3178C6" },
    { name: "Tailwind CSS", iconUrl: "https://cdn.simpleicons.org/tailwindcss/06B6D4" },
    { name: "FastAPI", iconUrl: "https://cdn.simpleicons.org/fastapi/009688" },
    { name: "Google Gemini", iconUrl: "https://cdn.simpleicons.org/googlegemini/8E75B2" },
    { name: "Python", iconUrl: "https://cdn.simpleicons.org/python/3776AB" }
  ];

  return (
    <div className="min-h-screen text-black flex flex-col items-center pb-24 selection:bg-blue-700 selection:text-white">
      
      {/* Custom styles for the horizontal rolling marquee */}
      <style>{`
        @keyframes scroll {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .marquee-container {
          overflow: hidden;
          width: 100%;
          padding: 1rem 0;
        }
        .marquee-content {
          display: flex;
          width: max-content;
          animation: scroll 30s linear infinite;
        }
        .marquee-content:hover {
          animation-play-state: paused;
        }
      `}</style>

      {/* Navbar */}
      <nav className="w-full max-w-7xl mx-auto px-6 md:px-12 py-6 flex justify-between items-center z-20">
        <div 
          className="rm-box px-4 py-2 font-black text-xl bg-white flex items-center gap-2"
          style={{ fontFamily: 'Helvetica, Arial, sans-serif' }}
        >
          <Sparkles className="w-5 h-5 text-blue-700" />
          ResumeTailor-AI
        </div>
        
        <a href="https://github.com/VJsharan/jd-to-resume-pdf" target="_blank" rel="noreferrer" className="rm-btn bg-blue-700 text-white hover:bg-blue-800 px-4 py-2 flex items-center gap-2">
          <Code className="w-5 h-5" /> GITHUB
        </a>
      </nav>

      <main className="w-full max-w-7xl mx-auto px-6 md:px-12 flex flex-col items-center mt-12 md:mt-24 space-y-24">
        
        {/* HERO SECTION */}
        <section className="flex flex-col items-center text-center w-full">
          <motion.h1 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-5xl md:text-7xl font-black font-serif leading-[1.1] tracking-tight max-w-4xl"
          >
            Instantly tailor your<br/>
            resume to <span className="bg-blue-700 text-white px-3 py-1 inline-block mt-2 transform -rotate-1 rounded-sm">any job description.</span>
          </motion.h1>
          <motion.p 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="text-xl md:text-2xl font-medium max-w-2xl text-gray-800 mt-8 mb-12"
          >
            Upload your master resume PDF, paste the job description, and let our AI perfectly format and optimize a new ATS-friendly PDF in seconds.
          </motion.p>
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <button onClick={onStart} className="rm-btn bg-orange-500 hover:bg-orange-600 text-white px-10 py-5 flex items-center gap-3 text-xl transition-transform hover:-translate-y-1">
              OPEN GENERATOR <ArrowRight className="w-6 h-6" />
            </button>
          </motion.div>
        </section>

        {/* TECH STACK SECTION (Scrolling Marquee) */}
        <section className="w-full text-center flex flex-col items-center">
          <h3 className="font-mono text-sm tracking-[0.2em] text-gray-500 uppercase font-bold mb-4">Built With</h3>
          <div className="marquee-container">
            <div className="marquee-content gap-6">
              {/* Render the array twice to create a seamless infinite loop */}
              {[...techStack, ...techStack].map((tech, index) => (
                <div 
                  key={index} 
                  className="rm-box bg-white flex items-center gap-3 px-6 py-4 cursor-pointer whitespace-nowrap transition-colors hover:bg-gray-50"
                  title="Hover to pause"
                >
                  <img src={tech.iconUrl} alt={tech.name} className="w-6 h-6 object-contain drop-shadow-sm" />
                  <span className="font-bold font-mono text-base">{tech.name}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FEATURES GRID */}
        <section className="w-full text-center space-y-10">
          <h2 className="text-4xl font-serif font-black tracking-tight">Features</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="rm-box bg-white text-black p-8 text-left space-y-4 hover:-translate-y-1 transition-transform">
              <h3 className="text-2xl font-serif font-bold text-blue-700">AI Analysis</h3>
              <p className="font-medium text-gray-700">Uses Google Gemini to perfectly map your existing skills and projects to the exact keywords algorithms are hunting for.</p>
            </div>
            <div className="rm-box bg-white text-black p-8 text-left space-y-4 hover:-translate-y-1 transition-transform">
              <h3 className="text-2xl font-serif font-bold text-orange-500">Auto Formatting</h3>
              <p className="font-medium text-gray-700">Generates a flawless, strictly 1-page PDF layout combining classic ATS-friendly structure using purely headless Playwright.</p>
            </div>
            <div className="rm-box bg-white text-black p-8 text-left space-y-4 hover:-translate-y-1 transition-transform">
              <h3 className="text-2xl font-serif font-bold text-pink-600">Knowledge Base</h3>
              <p className="font-medium text-gray-700">Can hook into a personal databank of expanded experiences to smartly swap out projects that fit the job better.</p>
            </div>
          </div>
        </section>

      </main>
      
      {/* Footer */}
      <footer className="w-full border-t-2 border-black bg-white mt-32">
        <div className="w-full max-w-7xl mx-auto p-12">
          <div className="flex flex-col md:flex-row justify-between items-center gap-8">
            <div 
              className="rm-box px-4 py-2 font-black text-lg flex items-center bg-white shadow-none border-2"
              style={{ fontFamily: 'Helvetica, Arial, sans-serif' }}
            >
              <Sparkles className="w-4 h-4 text-blue-700 inline mr-2" />
              ResumeTailor-AI
            </div>
            <div className="font-mono text-sm text-gray-600 font-medium">
               © {new Date().getFullYear()} Resume Tailor AI. Open source on GitHub.
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
