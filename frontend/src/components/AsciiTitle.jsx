export default function AsciiTitle() {
  const asciiArt = `
  _  __  ____   _____   _____  _____  _  __  _____ 
 | |/ / / __ \\ |  __ \\ |_   _||_   _|| |/ / |_   _|
 | ' / | |  | || |__) |  | |    | |  | ' /    | |  
 |  <  | |  | ||  ___/   | |    | |  |  <     | |  
 | . \\ | |__| || |      _| |_  _| |_ | . \\   _| |_ 
 |_|\\_\\ \\____/ |_|     |_____||_____||_|\\_\\ |_____|
  `;

  return (
    <div className="ascii-title-container">
      <pre className="ascii-title">{asciiArt}</pre>
    </div>
  );
}
