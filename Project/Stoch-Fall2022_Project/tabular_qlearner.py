# Copyright 2019 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tabular Q-learning agent."""

import collections
import numpy as np

from open_spiel.python import rl_agent
from open_spiel.python import rl_tools

try:
    from IPython import embed
except:
    pass


def info_state_to_board(time_step):
    info_state = time_step.observations["info_state"][0]
    x_locations = np.nonzero(info_state[9:18])[0]
    o_locations = np.nonzero(info_state[18:])[0]
    board = np.full(3 * 3, 0)
    board[x_locations] = 1
    board[o_locations] = -1
    board = np.reshape(board, (3, 3))
    return board

reward_mask = np.array([[0, 1, 0],
                        [1, 0, 1],
                        [0, 0, 0]])
reward_mask_count = np.sum(reward_mask)

def valuedict():
    #: The default factory is called without arguments to produce a new value when a key is not present, in __getitem__ only.
    #: This value is added to the dict, so modifying it will modify the dict.
    return collections.defaultdict(float)


class QLearner(rl_agent.AbstractAgent):
    """Tabular Q-Learning agent."""

    def __init__(
        self,
        player_id,
        num_actions,
        step_size=0.1,
        epsilon_schedule=rl_tools.ConstantSchedule(0.2),
        discount_factor=1.0,
        centralized=False,
    ):
        """Initialize the Q-Learning agent."""
        # super().__init__()
        self._player_id = player_id
        self._num_actions = num_actions
        self._step_size = step_size
        self._epsilon_schedule = epsilon_schedule
        self._epsilon = epsilon_schedule.value
        self._discount_factor = discount_factor
        self._centralized = centralized
        self._q_values = collections.defaultdict(valuedict)
        self._prev_info_state = None
        self._last_loss_value = None

    def _epsilon_greedy(self, info_state, legal_actions, epsilon):
        """Returns a valid epsilon-greedy action and valid action probs. (goes to a non-greedy state with probability epsilon, and to a greedy state with probability 1-epsilon)

        If the agent has not been to `info_state`, a valid random action is chosen.

        Args:
          info_state: hashable representation of the information state.
          legal_actions: list of actions at `info_state`.
          epsilon: float, prob of taking an exploratory action.

        Returns:
          A valid epsilon-greedy action and valid action probabilities.
        """

        if np.random.rand() < epsilon:
            action = np.random.choice(legal_actions)
            probs = np.zeros(self._num_actions)
            probs[action] = 1.0
            return action, probs
        probs = np.zeros(self._num_actions)
        for action in legal_actions:
            best_action = np.argmax(
                [self._q_values[info_state][action] for action in legal_actions]
            )
            probs[best_action] = 1.0


        action = np.random.choice(range(self._num_actions), p=probs)
        return action, probs

    def _get_action_probs(self, info_state, legal_actions, epsilon):
        """Returns a selected action and the probabilities of legal actions.

        To be overwritten by subclasses that implement other action selection
        methods.

        Args:
          info_state: hashable representation of the information state.
          legal_actions: list of actions at `info_state`.
          epsilon: float: current value of the epsilon schedule or 0 in case
            evaluation. QLearner uses it as the exploration parameter in
            epsilon-greedy, but subclasses are free to interpret in different ways
            (e.g. as temperature in softmax).
        """
        return self._epsilon_greedy(info_state, legal_actions, epsilon)

    def step(self, time_step, is_evaluation=False, top1=False):
        """Returns the action to be taken and updates the Q-values if needed.

        Args:
          time_step: an instance of rl_environment.TimeStep.
          is_evaluation: bool, whether this is a training or evaluation call.

        Returns:
          A `rl_agent.StepOutput` containing the action probs and chosen action.
        """
        if self._centralized:
            info_state = str(time_step.observations["info_state"])
        else:
            info_state = str(time_step.observations["info_state"][self._player_id])
        legal_actions = time_step.observations["legal_actions"][self._player_id]

        # Prevent undefined errors if this agent never plays until terminal step
        action, probs = None, None

        # Act step: don't act at terminal states.
        if not time_step.last():
            epsilon = 0.0 if is_evaluation else self._epsilon
            action, probs = self._get_action_probs(info_state, legal_actions, epsilon)
            if top1 or is_evaluation:
                action = np.argmax(probs)

        # Learn step: don't learn during evaluation or at first agent steps.
        if self._prev_info_state and not is_evaluation:
            reward = time_step.rewards[self._player_id]
            # Q-Learning update.
            # self._q_values[self._prev_info_state][self._prev_action] += self._step_size * (
            #     reward
            #     + self._discount_factor * self._q_values[info_state][action]
            #     - self._q_values[self._prev_info_state][self._prev_action]
            # )


            if time_step.last():
                target = reward
            else:
                # if there is any legal action, then we can use the q-values
                if len(legal_actions) > 0:
                    target = reward + self._discount_factor * max(
                        self._q_values[info_state][a] for a in legal_actions
                    )
                # if there is no legal action, then we can't use the q-values
                else:
                    target = reward

            self._q_values[self._prev_info_state][self._prev_action] += self._step_size * (
                    target - self._q_values[self._prev_info_state][self._prev_action]
            )

            # Update loss value
            self._last_loss_value = self._q_values[self._prev_info_state][self._prev_action] - target








            # @fillMe
            

            # Decay epsilon, if necessary.
            self._epsilon = self._epsilon_schedule.step()

            if time_step.last():  # prepare for the next episode.
                self._prev_info_state = None
                return

        # Don't mess up with the state during evaluation.
        if not is_evaluation:
            self._prev_info_state = info_state
            self._prev_action = action
        return rl_agent.StepOutput(action=action, probs=probs)

    def get_action_reward(self, time_step):
        """Returns the action to be taken and the reward to be given.

        Args:
          time_step: an instance of rl_environment.TimeStep.

        Returns:
          A `rl_agent.StepOutput` containing the action probs and chosen action.
        """
        return self.step(time_step)

    def eval_step(self, time_step):
        """Returns the action to be taken in evaluation.

        Args:
          time_step: an instance of rl_environment.TimeStep.

        Returns:
          A `rl_agent.StepOutput` containing the action probs and chosen action.
        """
        return self.step(time_step, is_evaluation=True)

    def eval_top1_step(self, time_step):
        """Returns the action to be taken in evaluation.

        Args:
          time_step: an instance of rl_environment.TimeStep.

        Returns:
          A `rl_agent.StepOutput` containing the action probs and chosen action.
        """
        return self.step(time_step, is_evaluation=True, top1=True)

    def get_loss(self):
        return self._last_loss_value

    def get_q_values(self):
        return self._q_values

    def get_epsilon(self):
        return self._epsilon

    def get_step_size(self):
        return self._step_size

# Local Variables:
# tab-width: 4
# End:
