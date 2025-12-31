import React from 'react';
import { Box, Toolbar } from '@mui/material';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { sidebarCollapsedWidth, sidebarWidth } from './layoutConstants';
import { TopBar } from './TopBar';

export function AppLayout(): React.JSX.Element {
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);
  const currentSidebarWidth = sidebarCollapsed ? sidebarCollapsedWidth : sidebarWidth;

  return (
    <Box sx={{ display: 'flex' }}>
      <TopBar
        sidebarWidth={currentSidebarWidth}
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={() => setSidebarCollapsed((c) => !c)}
      />
      <Sidebar collapsed={sidebarCollapsed} />
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: { sm: `calc(100% - ${currentSidebarWidth}px)` },
        }}
      >
        <Toolbar />
        <Outlet />
      </Box>
    </Box>
  );
}
