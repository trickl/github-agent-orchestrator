import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Button,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

type Props = {
  targetStateText: string;
  isStartingFirstIteration: boolean;
  onTargetStateChange: (value: string) => void;
  onStartFirstIteration: () => void;
  onSaveForLater: () => void;
};

const EXAMPLE_TARGET_PROMPTS = [
  'Add a new feature',
  'Fix failing tests',
  'Refactor a module',
  'Improve performance',
];

export function OnboardingTargetCard({
  targetStateText,
  isStartingFirstIteration,
  onTargetStateChange,
  onStartFirstIteration,
  onSaveForLater,
}: Props): React.JSX.Element {
  return (
    <Stack spacing={2.5}>
      <Typography variant="h4">What do you want to build?</Typography>
      <Typography color="text.secondary">
        Describe the desired end state. The agent will work toward this goal iteratively.
      </Typography>

      <TextField
        multiline
        minRows={8}
        value={targetStateText}
        onChange={(event) => onTargetStateChange(event.target.value)}
        placeholder="Implement a REST API for user authentication with login, registration, and tests."
        fullWidth
      />

      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        {EXAMPLE_TARGET_PROMPTS.map((prompt) => (
          <Chip
            key={prompt}
            label={prompt}
            onClick={() => {
              if (targetStateText.trim()) return;
              onTargetStateChange(prompt);
            }}
            variant="outlined"
          />
        ))}
      </Stack>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography>Advanced options</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stack spacing={2}>
            <FormControl fullWidth disabled>
              <InputLabel id="branch-behavior-label">Branch behaviour</InputLabel>
              <Select labelId="branch-behavior-label" label="Branch behaviour" value="default">
                <MenuItem value="default">Use default branch strategy</MenuItem>
              </Select>
            </FormControl>
            <FormControl fullWidth disabled>
              <InputLabel id="review-preferences-label">Review preferences</InputLabel>
              <Select labelId="review-preferences-label" label="Review preferences" value="standard">
                <MenuItem value="standard">Standard review cadence</MenuItem>
              </Select>
            </FormControl>
            <TextField disabled label="Iteration constraints" placeholder="Optional limits and constraints" />
          </Stack>
        </AccordionDetails>
      </Accordion>

      <Typography variant="body2" color="text.secondary">
        More specific goals produce better results.
      </Typography>

      <Stack direction="row" spacing={2}>
        <Button variant="contained" size="large" disabled={isStartingFirstIteration} onClick={onStartFirstIteration}>
          Start first iteration
        </Button>
        <Button variant="outlined" disabled={isStartingFirstIteration} onClick={onSaveForLater}>
          Save for later
        </Button>
      </Stack>
    </Stack>
  );
}
