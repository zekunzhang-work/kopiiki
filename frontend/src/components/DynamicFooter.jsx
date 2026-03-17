import React, { useState, useEffect } from 'react';

const DynamicFooter = () => {
  const [beijingTime, setBeijingTime] = useState('');
  const [tokyoTime, setTokyoTime] = useState('');

  useEffect(() => {
    const updateTimes = () => {
      const now = new Date();
      
      const timeOptions = { 
        hour: 'numeric', 
        minute: '2-digit', 
        second: '2-digit', 
        hour12: true 
      };

      setBeijingTime(now.toLocaleTimeString('en-US', { ...timeOptions, timeZone: 'Asia/Shanghai' }).toUpperCase());
      setTokyoTime(now.toLocaleTimeString('en-US', { ...timeOptions, timeZone: 'Asia/Tokyo' }).toUpperCase());
    };

    updateTimes();
    const intervalId = setInterval(updateTimes, 1000);

    return () => clearInterval(intervalId);
  }, []);

  return (
    <footer className="dynamic-footer">
      <div className="footer-left">
        BEIJING {beijingTime}
      </div>
      
      <div className="footer-right">
        TOKYO {tokyoTime}
      </div>
    </footer>
  );
};

export default DynamicFooter;
