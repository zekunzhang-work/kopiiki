import React, { useEffect, useRef } from 'react';

const TerminalCursor = () => {
  const canvasRef = useRef(null);
  const mouseRef = useRef({ x: -100, y: -100 });
  const cellsRef = useRef(new Map()); // Stores { col-row: opacity }

  // Configuration for the TUI grid
  const CELL_WIDTH = 8; // Dense grid 
  const CELL_HEIGHT = 16; 
  const DECAY_RATE = 0.05; // How fast the trail fades
  const FILL_COLOR = 'rgba(215, 215, 215, '; // Soft light gray

  // Track if we are hovering over an interactive UI element
  const hoveredRectRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let animationFrameId;

    // Handle resizing & HDPI
    const resizeCanvas = () => {
      const dpr = window.devicePixelRatio || 1;
      // Actual DOM size
      const rect = canvas.getBoundingClientRect();
      
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      
      ctx.scale(dpr, dpr);
    };
    
    // Initial size
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Track mouse
    const handleMouseMove = (e) => {
      mouseRef.current.x = e.clientX;
      mouseRef.current.y = e.clientY;

      const target = e.target;
      if (
        target && 
        ['A', 'BUTTON', 'INPUT'].includes(target.tagName) && 
        !target.classList.contains('url-input')
      ) {
        hoveredRectRef.current = target.getBoundingClientRect();
      } else if (target && (target.closest('a') || target.closest('button'))) {
        const el = target.closest('a') || target.closest('button');
        hoveredRectRef.current = el.getBoundingClientRect();
      } else {
        hoveredRectRef.current = null;
      }
    };
    
    window.addEventListener('mousemove', handleMouseMove);

    // Render loop
    const render = () => {
      // Clear using logical bounds since context is scaled
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

      let offsetX = 0;
      let offsetY = 0;

      // Find the input element to align grid and draw caret
      const inputEl = document.querySelector('.url-input');
      let isInputFocused = false;
      let caretX = -1;
      let caretY = -1;

      if (inputEl) {
        const rect = inputEl.getBoundingClientRect();
        // Offset the grid so mathematical columns perfectly align with text characters
        offsetX = rect.left % CELL_WIDTH;
        offsetY = rect.top % CELL_HEIGHT;

        if (document.activeElement === inputEl) {
          isInputFocused = true;
          // Calculate caret coordinate, including scroll tracking for long text
          const charCount = inputEl.selectionStart || 0;
          caretX = rect.left + (charCount * CELL_WIDTH) - inputEl.scrollLeft;
          caretY = rect.top;
        }
      }

      const msx = mouseRef.current.x;
      const msy = mouseRef.current.y;
      
      // Calculate current grid cell considering offset
      const currentCol = Math.floor((msx - offsetX) / CELL_WIDTH);
      const currentRow = Math.floor((msy - offsetY) / CELL_HEIGHT);
      const currentKey = `${currentCol}-${currentRow}`;

      // Set current cell to max opacity if mouse is active on screen AND input isn't focused
      if (msx >= 0 && msy >= 0 && !isInputFocused) {
        cellsRef.current.set(currentKey, 1.0);
      }

        // If hovering over an interactive structural element, highlight all underlying grid cells
        if (hoveredRectRef.current) {
          const rect = hoveredRectRef.current;
          // Calculate the grid cell boundaries that completely encompass this DOM rect
          const startCol = Math.floor((rect.left - offsetX) / CELL_WIDTH);
          const endCol = Math.ceil((rect.right - offsetX) / CELL_WIDTH);
          const startRow = Math.floor((rect.top - offsetY) / CELL_HEIGHT);
          const endRow = Math.ceil((rect.bottom - offsetY) / CELL_HEIGHT);

          // Force these specific cells to stay fully opaque while hovered
          for (let col = startCol; col < endCol; col++) {
            for (let row = startRow; row < endRow; row++) {
              const key = `${col}-${row}`;
              cellsRef.current.set(key, 0.5); // Solid but subtle highlight block overlay
            }
          }
        }

        // Draw all active cells
      for (const [key, opacity] of cellsRef.current.entries()) {
        const [col, row] = key.split('-').map(Number);
        
        // Use Math.round to prevent sub-pixel blur rendering on HDPI
        const x = Math.round(col * CELL_WIDTH + offsetX);
        const y = Math.round(row * CELL_HEIGHT + offsetY);

        // Draw the block
        ctx.fillStyle = `${FILL_COLOR}${opacity})`;
        ctx.fillRect(x, y, CELL_WIDTH, CELL_HEIGHT);

        // Decay
        const newOpacity = opacity - DECAY_RATE;
        if (newOpacity <= 0) {
          cellsRef.current.delete(key);
        } else {
          cellsRef.current.set(key, newOpacity);
        }
      }

      // Draw pulsing caret if focused
      if (isInputFocused && caretX >= 0) {
        // Pulse alpha between 0.2 and 0.8
        const time = Date.now();
        const pulse = (Math.sin(time / 150) + 1) / 2; // 0 to 1
        const alpha = 0.2 + (pulse * 0.6);
        ctx.fillStyle = `${FILL_COLOR}${alpha})`;
        
        const cx = Math.round(caretX);
        const cy = Math.round(caretY);
        ctx.fillRect(cx, cy, CELL_WIDTH, CELL_HEIGHT);
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      window.removeEventListener('mousemove', handleMouseMove);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        pointerEvents: 'none',
        zIndex: -1, // Sinks underneath the logo and text
        opacity: 0.6 // Slightly transparent TUI block look
      }}
    />
  );
};

export default TerminalCursor;
