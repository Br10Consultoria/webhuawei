// Função para atualizar o terminal
function updateTerminal(command, output) {
    term.writeln(`$ ${command}`);
    term.writeln(output);
    term.writeln('');
}

// Função para replay de comando
async function replayCommand(commandId) {
    try {
        const response = await fetch(`/api/replay_command/${commandId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        const data = await response.json();
        
        if (data.success) {
            updateTerminal(data.command, data.output);
        }
    } catch (error) {
        console.error('Error replaying command:', error);
    }
}

// Atualizar gráficos em tempo real
function updateCharts(newData) {
    commandHistoryChart.data.datasets[0].data = newData.commandCounts;
    commandHistoryChart.update();
    
    responseTimeChart.data.datasets[0].data = newData.responseTimes;
    responseTimeChart.update();
} 