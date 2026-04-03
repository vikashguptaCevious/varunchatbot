import React, { useState, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const Navbar: React.FC = () => {
    const { isAdmin, logout } = useAuth();
    const [menuOpen, setMenuOpen] = useState(false);
    const location = useLocation();

    useEffect(() => {
        setMenuOpen(false);
    }, [location.pathname]);

    useEffect(() => {
        const onResize = () => {
            if (window.innerWidth > 768) setMenuOpen(false);
        };
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
    }, []);

    const linkClass = ({ isActive }: { isActive: boolean }) =>
        isActive ? 'nav-link active' : 'nav-link';

    return (
        <nav className="navbar">
            <div className="navbar-inner">
                <h1 className="navbar-title">MiniRAG</h1>
                <div className={`nav-links ${menuOpen ? 'is-open' : ''}`}>
                    <NavLink to="/" className={linkClass} onClick={() => setMenuOpen(false)}>
                        Query Agent
                    </NavLink>
                    {isAdmin && (
                        <NavLink to="/add" className={linkClass} onClick={() => setMenuOpen(false)}>
                            Add Content
                        </NavLink>
                    )}
                    {isAdmin ? (
                        <button type="button" className="nav-btn-logout" onClick={() => { logout(); setMenuOpen(false); }}>
                            Logout
                        </button>
                    ) : (
                        <NavLink to="/login" className={linkClass} onClick={() => setMenuOpen(false)}>
                            Admin
                        </NavLink>
                    )}
                </div>
                <button
                    type="button"
                    className="nav-menu-toggle"
                    aria-label={menuOpen ? 'Close menu' : 'Open menu'}
                    aria-expanded={menuOpen}
                    onClick={() => setMenuOpen((o) => !o)}
                >
                    {menuOpen ? '✕' : '☰'}
                </button>
            </div>
        </nav>
    );
};

export default Navbar;
