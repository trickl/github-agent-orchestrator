import React from 'react';
import {
  Divider,
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Tooltip,
} from '@mui/material';
import DashboardIcon from '@mui/icons-material/Dashboard';
import AutorenewIcon from '@mui/icons-material/Autorenew';
import TimelineIcon from '@mui/icons-material/Timeline';
import AssignmentTurnedInIcon from '@mui/icons-material/AssignmentTurnedIn';
import BugReportIcon from '@mui/icons-material/BugReport';
import RuleIcon from '@mui/icons-material/Rule';
import DescriptionIcon from '@mui/icons-material/Description';
import { NavLink, useLocation } from 'react-router-dom';

import { sidebarCollapsedWidth, sidebarWidth } from './layoutConstants';

type SidebarProps = {
  collapsed: boolean;
};

export function Sidebar({ collapsed }: SidebarProps): React.JSX.Element {
  const location = useLocation();

  const drawerWidth: number = collapsed ? sidebarCollapsedWidth : sidebarWidth;

  const items: Array<{
    label: string;
    to: string;
    icon: React.JSX.Element;
  }> = [
    { label: 'Overview', to: '/', icon: <DashboardIcon fontSize="small" /> },
    { label: 'Loop', to: '/loop', icon: <AutorenewIcon fontSize="small" /> },
    { label: 'Timeline', to: '/timeline', icon: <TimelineIcon fontSize="small" /> },
    { label: 'Active Work', to: '/active', icon: <AssignmentTurnedInIcon fontSize="small" /> },
    { label: 'Issues', to: '/issues', icon: <BugReportIcon fontSize="small" /> },
    { label: 'Cognitive Tasks', to: '/cognitive-tasks', icon: <RuleIcon fontSize="small" /> },
    { label: 'Planning Docs', to: '/docs', icon: <DescriptionIcon fontSize="small" /> },
  ];

  return (
    <Drawer
      variant="permanent"
      sx={{
        width: drawerWidth,
        flexShrink: 0,
        [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: 'border-box' },
      }}
    >
      <Toolbar />
      <Divider />
      <List>
        {items.map((item) => (
          <Tooltip
            key={item.to}
            title={collapsed ? item.label : ''}
            placement="right"
            arrow
            disableHoverListener={!collapsed}
          >
            <ListItemButton
              component={NavLink}
              to={item.to}
              selected={location.pathname === item.to}
              sx={{
                justifyContent: collapsed ? 'center' : 'flex-start',
                px: collapsed ? 1 : 2,
              }}
            >
              <ListItemIcon
                sx={{
                  minWidth: collapsed ? 0 : 40,
                  mr: collapsed ? 0 : 1,
                  justifyContent: 'center',
                }}
              >
                {item.icon}
              </ListItemIcon>
              {collapsed ? null : <ListItemText primary={item.label} />}
            </ListItemButton>
          </Tooltip>
        ))}
      </List>
    </Drawer>
  );
}
