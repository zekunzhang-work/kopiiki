import React from 'react';
import { GithubLogoIcon, XLogoIcon } from '@phosphor-icons/react';

const TopNav = ({ onHistoryClick, onReadmeClick }) => {
  return (
    <nav className="top-nav">
      <button type="button" onClick={onHistoryClick} className="nav-link nav-button">HISTORY</button>
      <button type="button" onClick={onReadmeClick} className="nav-link nav-button">README</button>
      <a href="https://www.zhangzekun.com" target="_blank" rel="noopener noreferrer" className="nav-link">CONTACT</a>
      <span className="top-nav-social">
        <a href="https://github.com/shioramen/kopiiki" target="_blank" rel="noopener noreferrer" className="nav-link nav-icon-link" aria-label="GitHub" title="GitHub">
          <GithubLogoIcon size={16} weight="bold" />
        </a>
        <a href="https://x.com/shioramen_x" target="_blank" rel="noopener noreferrer" className="nav-link nav-icon-link" aria-label="Twitter" title="Twitter">
          <XLogoIcon size={15} weight="bold" />
        </a>
      </span>
    </nav>
  );
};

export default TopNav;
