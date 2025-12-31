import React from 'react';
import {
  Divider,
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
} from '@mui/material';
import DashboardIcon from '@mui/icons-material/Dashboard';
import TimelineIcon from '@mui/icons-material/Timeline';
import AssignmentTurnedInIcon from '@mui/icons-material/AssignmentTurnedIn';
import BugReportIcon from '@mui/icons-material/BugReport';
import RuleIcon from '@mui/icons-material/Rule';
import DescriptionIcon from '@mui/icons-material/Description';
import { NavLink, useLocation } from 'react-router-dom';

import { sidebarWidth } from './layoutConstants';

export function Sidebar(): React.JSX.Element {
  const location = useLocation();

  const items: Array<{
    label: string;
    to: string;
    icon: React.JSX.Element;
  }> = [
    { label: 'Overview', to: '/', icon: <DashboardIcon fontSize="small" /> },
    { label: 'Timeline', to: '/timeline', icon: <TimelineIcon fontSize="small" /> },
    { label: 'Active Work', to: '/active', icon: <AssignmentTurnedInIcon fontSize="small" /> },
    { label: 'Issues', to: '/issues', icon: <BugReportIcon fontSize="small" /> },
    { label: 'Generation Rules', to: '/rules', icon: <RuleIcon fontSize="small" /> },
    { label: 'Planning Docs', to: '/docs', icon: <DescriptionIcon fontSize="small" /> },
  ];

  return (
    <Drawer
      variant="permanent"
      sx={{
        width: sidebarWidth,
        flexShrink: 0,
        [`& .MuiDrawer-paper`]: { width: sidebarWidth, boxSizing: 'border-box' },
      }}
    >
      <Toolbar />
      <Divider />
      <List>
        {items.map((item) => (
          <ListItemButton
            key={item.to}
            component={NavLink}
            to={item.to}
            selected={location.pathname === item.to}
          >
            <ListItemIcon>{item.icon}</ListItemIcon>
            <ListItemText primary={item.label} />
          </ListItemButton>
        ))}
      </List>
    </Drawer>
  );
}
