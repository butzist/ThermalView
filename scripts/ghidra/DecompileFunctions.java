// Decompile every function whose name matches a filter and print C-like output.
//
// Cutter/REA are not required: this is the same decompiler the Ghidra GUI uses,
// driven fully headless.
//
// Usage:
//   ghidra-analyzeHeadless PROJDIR PROJ -import BINARY \
//     -scriptPath scripts/ghidra -postScript DecompileFunctions.java [FILTER]
//
// FILTER is a case-sensitive substring of the function name; the default
// "Java_" selects JNI exports.
//
//@category ThermalView
//@keybinding
//@menupath
//@toolbar

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.util.task.ConsoleTaskMonitor;

public class DecompileFunctions extends GhidraScript {

	private static final int TIMEOUT_SECONDS = 180;

	@Override
	public void run() throws Exception {
		String filter = "Java_";
		String[] args = getScriptArgs();
		if (args.length > 0) {
			filter = args[0];
		}

		DecompInterface decompiler = new DecompInterface();
		decompiler.openProgram(currentProgram);
		ConsoleTaskMonitor monitor = new ConsoleTaskMonitor();

		int found = 0;
		int done = 0;
		FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
		while (it.hasNext() && !monitor.isCancelled()) {
			Function f = it.next();
			if (!f.getName().contains(filter)) {
				continue;
			}
			found++;
			DecompileResults results = decompiler.decompileFunction(f, TIMEOUT_SECONDS, monitor);
			println("");
			println("/* " + f.getName() + " @ " + f.getEntryPoint() + " */");
			if (results != null && results.decompileCompleted()) {
				println(results.getDecompiledFunction().getC());
				done++;
			}
			else {
				println("/* decompilation failed: " +
					(results == null ? "no result" : results.getErrorMessage()) + " */");
			}
		}
		println("");
		println("/* filter \"" + filter + "\": " + done + "/" + found + " function(s) decompiled */");
		decompiler.dispose();
	}
}
